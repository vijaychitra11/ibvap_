import itertools, os, secrets, shutil, tempfile, json, threading, time
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import cv2
from . import models, schemas
from .database import engine, get_db, SessionLocal, Base
from .seed import seed_if_empty
from .analytics.detection import detect_image, detect_frame, models_status, ModelUnavailableError
from .analytics.night import analyze_brightness
from .analytics.video import analyze_video
from .analytics.fence import inside_polygon, centroid
from .analytics.face import detect_faces as _detect_faces_raw
load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
Base.metadata.create_all(bind=engine)
with SessionLocal() as db: seed_if_empty(db)
app=FastAPI(title='IBVAP API',version='2.0.0',description='Intelligent Border Video Analytics Platform')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
_alert_seq=itertools.count(10000)
_live={}; _lock=threading.Lock()
_sessions={}  # token -> operator_id. In-memory; resets on restart (fine for a single-instance ops deployment).

def now(): return datetime.utcnow().strftime('%H:%M:%S Z · Today')
def create_alert(db,severity,title,description):
    a=models.Alert(ref_code=f'#AL-{next(_alert_seq)}',severity=severity,title=title,description=description,timestamp='Just now'); db.add(a); db.commit(); db.refresh(a); return a

def temp_upload(file):
    suffix=os.path.splitext(file.filename or '.bin')[1] or '.bin'
    tmp=tempfile.NamedTemporaryFile(delete=False,suffix=suffix); shutil.copyfileobj(file.file,tmp); tmp.close(); return tmp.name

def require_auth(authorization:Optional[str]=Header(None)):
    """Every mutating/operational endpoint depends on this. A missing or unknown
    bearer token is rejected outright — fixes the previous state where /auth/login
    issued a token that nothing ever checked."""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401,'Missing bearer token. Call /auth/login first.')
    token=authorization.split(' ',1)[1].strip()
    operator=_sessions.get(token)
    if not operator: raise HTTPException(401,'Invalid or expired session token.')
    return operator

def check_watchlist(db,plate_text,camera,sector):
    """Cross-check a read plate against active watchlist entries and escalate."""
    if not plate_text: return None
    norm=plate_text.strip().upper().replace(' ','')
    for w in db.query(models.WatchlistPlate).filter(models.WatchlistPlate.active==True).all():
        if w.plate.strip().upper().replace(' ','')==norm:
            return create_alert(db,'critical','Watchlist vehicle detected',f'Plate {plate_text} ({w.label or "flagged"}) detected at {camera or "unknown camera"}, {sector or "unknown sector"}.')
    return None

@app.get('/api/status')
def api_status(): return {'service':'IBVAP API','status':'online','version':'2.0.0','analytics':['human_detection','vehicle_classification','face_detection','anpr','virtual_fence','suspicious_activity','night_movement','tracking','alerts']}
@app.post('/auth/login',response_model=schemas.LoginResponse)
def login(payload:schemas.LoginRequest):
    if not payload.operator_id or not payload.passcode: raise HTTPException(401,'Invalid credentials')
    token=secrets.token_hex(16); _sessions[token]=payload.operator_id
    return schemas.LoginResponse(ok=True,operator_id=payload.operator_id,token=token)

@app.get('/cameras',response_model=List[schemas.CameraOut])
def list_cameras(db:Session=Depends(get_db)): return db.query(models.Camera).all()
@app.post('/cameras',response_model=schemas.CameraOut,status_code=201)
def create_camera(payload:schemas.CameraCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=models.Camera(**payload.model_dump()); db.add(x); db.commit(); db.refresh(x); return x
@app.put('/cameras/{camera_id}',response_model=schemas.CameraOut)
def update_camera(camera_id:int,payload:schemas.CameraCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=db.get(models.Camera,camera_id)
    if not x: raise HTTPException(404,'Camera not found')
    for k,v in payload.model_dump().items(): setattr(x,k,v)
    db.commit(); db.refresh(x); return x
@app.delete('/cameras/{camera_id}',status_code=204)
def delete_camera(camera_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=db.get(models.Camera,camera_id)
    if not x: raise HTTPException(404,'Camera not found')
    db.delete(x); db.commit()

@app.get('/alerts',response_model=List[schemas.AlertOut])
def list_alerts(db:Session=Depends(get_db)): return db.query(models.Alert).order_by(models.Alert.id.desc()).all()
@app.post('/alerts',response_model=schemas.AlertOut,status_code=201)
def create_alert_api(payload:schemas.AlertCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)): return create_alert(db,payload.severity,payload.title,payload.description)
@app.put('/alerts/{alert_id}',response_model=schemas.AlertOut)
def update_alert(alert_id:int,payload:schemas.AlertCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    a=db.get(models.Alert,alert_id)
    if not a: raise HTTPException(404,'Alert not found')
    a.severity=payload.severity;a.title=payload.title;a.description=payload.description;db.commit();db.refresh(a);return a
@app.delete('/alerts/{alert_id}',status_code=204)
def delete_alert(alert_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    a=db.get(models.Alert,alert_id)
    if not a: raise HTTPException(404,'Alert not found')
    db.delete(a);db.commit()

@app.get('/analytics/models/status',response_model=schemas.ModelsStatusOut)
def get_models_status(): return models_status()
@app.get('/analytics/anpr',response_model=List[schemas.ANPRRecordOut])
def list_anpr(db:Session=Depends(get_db)): return db.query(models.ANPRRecord).order_by(models.ANPRRecord.id.desc()).all()
@app.post('/analytics/anpr/scan')
async def scan_anpr(file:UploadFile=File(...),camera:str=Form(''),sector:str=Form(''),db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    path=temp_upload(file)
    try:
        try:r=detect_image(path,require_plate=False)
        except ModelUnavailableError as e: raise HTTPException(503,str(e))
        created=[]
        for p in r['plates']:
            text=(p.get('text') or '').strip(); c=int(round(p.get('confidence',0)*100)); rec=models.ANPRRecord(plate=text or 'UNREADABLE',camera=camera,sector=sector,status='Detected' if text else 'Unreadable',confidence=c,timestamp='Just now');db.add(rec);created.append(rec)
            if text:
                create_alert(db,'warning','ANPR vehicle identified',f'Plate {text} detected at {camera or "unknown camera"}.')
                check_watchlist(db,text,camera,sector)
        db.commit();[db.refresh(x) for x in created]
        return {'vehicles':r['vehicles'],'faces':r['faces'],'plates_detected':len(r['plates']),'records_created':[schemas.ANPRRecordOut.model_validate(x) for x in created]}
    finally: os.remove(path) if os.path.exists(path) else None

@app.get('/analytics/night',response_model=List[schemas.NightEventOut])
def list_night(db:Session=Depends(get_db)): return db.query(models.NightEvent).order_by(models.NightEvent.id.desc()).all()
@app.post('/analytics/night/scan')
async def scan_night(file:UploadFile=File(...),camera:str=Form(''),sector:str=Form(''),db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    path=temp_upload(file)
    try:
        a=analyze_brightness(path); event=None
        if a['is_night']:
            event=models.NightEvent(camera=camera,sector=sector,description=f"Low-light frame detected ({a['mean_brightness']} mean brightness)",brightness=int(a['mean_brightness']),timestamp='Just now');db.add(event);db.commit();db.refresh(event)
            create_alert(db,'info','Low-light condition detected',f'{camera or "Camera"} in {sector or "unknown sector"} has low-light conditions.')
        return {**a,'event_created':schemas.NightEventOut.model_validate(event) if event else None}
    finally: os.remove(path) if os.path.exists(path) else None

@app.get('/analytics/events',response_model=List[schemas.AnalyticsEventOut])
def list_events(limit:int=100,db:Session=Depends(get_db)): return db.query(models.AnalyticsEvent).order_by(models.AnalyticsEvent.id.desc()).limit(min(limit,500)).all()
@app.get('/analytics/summary')
def analytics_summary(db:Session=Depends(get_db)):
    ev=db.query(models.AnalyticsEvent).all(); anpr=db.query(models.ANPRRecord).count(); night=db.query(models.NightEvent).count()
    by={};
    for e in ev: by[e.event_type]=by.get(e.event_type,0)+1
    return {'events_total':len(ev),'anpr_reads':anpr,'night_events':night,'by_type':by,'models':models_status()}

@app.post('/analytics/video/upload')
async def upload_video(file:UploadFile=File(...),camera:str=Form(''),sector:str=Form(''),sample_every:int=Form(10),db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    ext=os.path.splitext(file.filename or '')[1].lower(); allowed={'.mp4','.avi','.mov','.mkv','.webm','.m4v'}
    if ext not in allowed: raise HTTPException(400,f'Unsupported video format: {ext or "unknown"}')
    path=temp_upload(file)
    try:
        settings=db.query(models.FenceSettings).first(); polygons=[]
        for z in db.query(models.FencePolygon).filter(models.FencePolygon.enabled==True).all():
            try: pts=json.loads(z.points_json)
            except: pts=[]
            if not z.camera or z.camera==camera: polygons.append({'name':z.name,'points':pts,'enabled':z.enabled})
        profiles=[]
        for p in db.query(models.FaceProfile).filter(models.FaceProfile.active==True).all(): profiles.append({'name':p.name,'embedding':json.loads(p.embedding_json)})
        result=analyze_video(path,sample_every=max(1,min(sample_every,300)),max_frames=600,fence_polygons=polygons,face_profiles=profiles,sensitivity=settings.sensitivity if settings else 3)
        result['camera']=camera;result['sector']=sector
        for e in result['analysis']['events']:
            ae=models.AnalyticsEvent(event_type=e['type'],severity=e['severity'],camera=camera,sector=sector,description=e['description'],confidence=e.get('confidence',0),frame=e.get('frame',0),time_seconds=e.get('time_seconds',0),metadata_json=json.dumps(e.get('metadata',{})));db.add(ae)
            create_alert(db,e['severity'],e['type'].replace('_',' ').title(),e['description'])
        for p in result['analysis']['plate_detections']:
            if p.get('text'):
                db.add(models.ANPRRecord(plate=p['text'],camera=camera,sector=sector,vehicle_type='',status='Detected',confidence=int(p.get('confidence',0)*100),timestamp='Video'))
                check_watchlist(db,p['text'],camera,sector)
        if result['analysis']['low_light_frames']:
            db.add(models.NightEvent(camera=camera,sector=sector,description=f"{result['analysis']['low_light_frames']} sampled low-light frames",brightness=0,timestamp='Video'))
        db.commit(); return result
    finally: os.remove(path) if os.path.exists(path) else None

@app.post('/analytics/image/analyze')
async def analyze_image(file:UploadFile=File(...),camera:str=Form(''),sector:str=Form(''),db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    path=temp_upload(file)
    try:
        profiles=[]
        for p in db.query(models.FaceProfile).filter(models.FaceProfile.active==True).all(): profiles.append({'name':p.name,'embedding':json.loads(p.embedding_json)})
        try: r=detect_image(path,require_plate=False,face_profiles=profiles)
        except ModelUnavailableError as e: raise HTTPException(503,str(e))
        events_created=[]
        for f in r.get('faces',[]):
            match=f.get('match','Unknown')
            if match and match!='Unknown':
                ae=models.AnalyticsEvent(event_type='face_match',severity='warning',camera=camera,sector=sector,description=f'Recognized profile match: {match}',confidence=f.get('match_confidence',0),frame=0,time_seconds=0,metadata_json=json.dumps({'name':match}));db.add(ae);events_created.append('face_match')
                create_alert(db,'warning','Face match',f'{match} recognized at {camera or "unknown camera"}.')
        for p in r.get('plates',[]):
            text=(p.get('text') or '').strip()
            if text:
                db.add(models.ANPRRecord(plate=text,camera=camera,sector=sector,status='Detected',confidence=int(round(p.get('confidence',0)*100)),timestamp='Image'))
                create_alert(db,'warning','ANPR vehicle identified',f'Plate {text} detected at {camera or "unknown camera"}.')
                check_watchlist(db,text,camera,sector)
        try:
            a=analyze_brightness(path)
            if a['is_night'] and (r.get('vehicles') or r.get('faces')):
                db.add(models.NightEvent(camera=camera,sector=sector,description=f"Low-light frame detected ({a['mean_brightness']} mean brightness)",brightness=int(a['mean_brightness']),timestamp='Image'))
                create_alert(db,'info','Low-light condition detected',f'{camera or "Camera"} in {sector or "unknown sector"} has low-light conditions.')
                r['night']=a
        except Exception: pass
        db.commit()
        return r
    finally: os.remove(path) if os.path.exists(path) else None

@app.post('/analytics/frame/detect')
async def detect_frame_lightweight(file:UploadFile=File(...),_op:str=Depends(require_auth)):
    """Fast, side-effect-free detection for a single frame — no DB writes, no
    alerts, no ANPR records. Built for live-preview loops (e.g. scrubbing a
    video and detecting frame-by-frame as it plays) where we don't want every
    captured frame spamming the alerts/events tables."""
    path=temp_upload(file)
    try:
        try: r=detect_image(path,require_plate=False)
        except ModelUnavailableError as e: raise HTTPException(503,str(e))
        return {'vehicles':r.get('vehicles',[]),'plates':r.get('plates',[])}
    finally: os.remove(path) if os.path.exists(path) else None

@app.post('/fence/zones',response_model=schemas.FenceZoneOut,status_code=201)
def create_zone(payload:schemas.FenceZoneCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    z=models.FenceZone(**payload.model_dump());db.add(z);db.commit();db.refresh(z);return z
@app.get('/fence/zones',response_model=List[schemas.FenceZoneOut])
def list_zones(db:Session=Depends(get_db)): return db.query(models.FenceZone).all()
@app.put('/fence/zones/{zone_id}',response_model=schemas.FenceZoneOut)
def update_zone(zone_id:int,payload:schemas.FenceZoneCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    z=db.get(models.FenceZone,zone_id)
    if not z: raise HTTPException(404,'Zone not found')
    z.name=payload.name;z.status=payload.status;db.commit();db.refresh(z);return z
@app.delete('/fence/zones/{zone_id}',status_code=204)
def delete_zone(zone_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    z=db.get(models.FenceZone,zone_id)
    if not z: raise HTTPException(404,'Zone not found')
    db.delete(z);db.commit()
@app.get('/fence/settings',response_model=schemas.FenceSettingsOut)
def get_settings(db:Session=Depends(get_db)): return db.query(models.FenceSettings).first()
@app.patch('/fence/settings',response_model=schemas.FenceSettingsOut)
def patch_settings(payload:schemas.FenceSettingsUpdate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    s=db.query(models.FenceSettings).first()
    for k,v in payload.model_dump(exclude_none=True).items(): setattr(s,k,v)
    db.commit();db.refresh(s);return s

@app.get('/fence/polygons',response_model=List[schemas.FencePolygonOut])
def polygons(db:Session=Depends(get_db)):
    out=[]
    for z in db.query(models.FencePolygon).all(): out.append({'id':z.id,'name':z.name,'camera':z.camera,'sector':z.sector,'points':json.loads(z.points_json),'enabled':z.enabled})
    return out
@app.post('/fence/polygons',response_model=schemas.FencePolygonOut,status_code=201)
def create_polygon(payload:schemas.FencePolygonCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    z=models.FencePolygon(name=payload.name,camera=payload.camera,sector=payload.sector,points_json=json.dumps(payload.points),enabled=payload.enabled);db.add(z);db.commit();db.refresh(z);return {'id':z.id,**payload.model_dump()}
@app.delete('/fence/polygons/{polygon_id}',status_code=204)
def delete_polygon(polygon_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    z=db.get(models.FencePolygon,polygon_id)
    if not z: raise HTTPException(404,'Polygon not found')
    db.delete(z);db.commit()

@app.get('/watchlist/plates',response_model=List[schemas.WatchlistPlateOut])
def watchlist(db:Session=Depends(get_db)): return db.query(models.WatchlistPlate).all()
@app.post('/watchlist/plates',response_model=schemas.WatchlistPlateOut,status_code=201)
def add_watchlist(payload:schemas.WatchlistPlateCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=models.WatchlistPlate(**payload.model_dump());db.add(x);db.commit();db.refresh(x);return x
@app.delete('/watchlist/plates/{item_id}',status_code=204)
def del_watchlist(item_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=db.get(models.WatchlistPlate,item_id)
    if not x: raise HTTPException(404,'Watchlist entry not found')
    db.delete(x);db.commit()

@app.post('/faces/profiles',response_model=schemas.FaceProfileOut,status_code=201)
def add_face_profile(payload:schemas.FaceProfileCreate,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=models.FaceProfile(name=payload.name,embedding_json=json.dumps(payload.embedding),active=payload.active);db.add(x);db.commit();db.refresh(x);return x
@app.get('/faces/profiles',response_model=List[schemas.FaceProfileOut])
def face_profiles(db:Session=Depends(get_db)):
    return db.query(models.FaceProfile).all()

@app.post('/faces/enroll',response_model=schemas.FaceProfileOut,status_code=201)
async def enroll_face(name:str=Form(...),file:UploadFile=File(...),db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    """Register a known-person profile straight from a photo, instead of requiring
    the caller to hand-craft an embedding vector (the only way /faces/profiles ever worked)."""
    path=temp_upload(file)
    try:
        import cv2
        img=cv2.imread(path)
        if img is None: raise HTTPException(400,'Could not read uploaded image')
        faces=_detect_faces_raw(img)
        if not faces: raise HTTPException(422,'No face detected in the uploaded photo — use a clear, front-facing shot.')
        best=max(faces,key=lambda f:(f['box'][2]-f['box'][0])*(f['box'][3]-f['box'][1]))
        x=models.FaceProfile(name=name,embedding_json=json.dumps(best['embedding']),active=True);db.add(x);db.commit();db.refresh(x)
        return x
    finally: os.remove(path) if os.path.exists(path) else None
@app.delete('/faces/profiles/{profile_id}',status_code=204)
def delete_face_profile(profile_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    x=db.get(models.FaceProfile,profile_id)
    if not x: raise HTTPException(404,'Profile not found')
    db.delete(x);db.commit()

def _stream_worker(camera_id,rtsp_url,stop_event,analyze_interval_s=5):
    """Actually opens the camera's RTSP feed and runs the same detection pipeline
    used for uploaded video, on a timer, writing events/alerts to the DB. Previously
    /streams/start only flipped a boolean and never touched the RTSP URL at all."""
    cap=cv2.VideoCapture(rtsp_url)
    opened=cap.isOpened()
    with _lock:
        _live.setdefault(camera_id,{})
        _live[camera_id]['connected']=opened
        if not opened: _live[camera_id]['error']='Could not open RTSP stream (unreachable, wrong URL, or unsupported codec).'
    if not opened:
        with _lock: _live[camera_id]['running']=False
        return
    last_analysis=0.0
    try:
        with SessionLocal() as db:
            settings=db.query(models.FenceSettings).first()
            polygons=[]
            for z in db.query(models.FencePolygon).filter(models.FencePolygon.enabled==True).all():
                try: pts=json.loads(z.points_json)
                except Exception: pts=[]
                polygons.append({'name':z.name,'points':pts,'enabled':z.enabled})
            profiles=[{'name':p.name,'embedding':json.loads(p.embedding_json)} for p in db.query(models.FaceProfile).filter(models.FaceProfile.active==True).all()]
            cam=db.get(models.Camera,camera_id); camera_name=cam.name if cam else str(camera_id); sector=cam.sector if cam else ''
            while not stop_event.is_set():
                ok,frame=cap.read()
                if not ok:
                    time.sleep(1.0)
                    with _lock: _live[camera_id]['connected']=False
                    continue
                with _lock: _live[camera_id]['connected']=True
                # Keep the newest camera frame for the browser MJPEG feed.
                with _lock:
                    _live[camera_id]['latest_frame']=frame.copy()
                t=time.time()
                if t-last_analysis>=analyze_interval_s:
                    last_analysis=t
                    try:
                        result=detect_frame(frame,require_plate=False,face_profiles=profiles)
                        # Draw analytics overlays on the frame shown to the frontend.
                        for v in result.get('vehicles',[]):
                            x1,y1,x2,y2=v['box']; cv2.rectangle(frame,(x1,y1),(x2,y2),(0,220,120),2); cv2.putText(frame,v['type'],(x1,max(18,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,220,120),2)
                        for p in result.get('plates',[]):
                            x1,y1,x2,y2=p['box']; cv2.rectangle(frame,(x1,y1),(x2,y2),(0,180,255),2); cv2.putText(frame,p.get('text') or 'PLATE',(x1,max(18,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,180,255),2)
                        for f in result.get('faces',[]):
                            x1,y1,x2,y2=f['box']; cv2.rectangle(frame,(x1,y1),(x2,y2),(180,80,255),2)
                        ok_jpg,buf=cv2.imencode('.jpg',frame)
                        if ok_jpg:
                            with _lock: _live[camera_id]['latest_jpeg']=buf.tobytes()
                        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY); brightness=float(gray.mean())
                        summary={'vehicles':len(result['vehicles']),'faces':len(result['faces']),'plates':len(result['plates']),'brightness':round(brightness,1),'is_night':brightness<55}
                        for v in result['vehicles']:
                            p=centroid(v['box'])
                            for z in polygons:
                                if z['enabled'] and inside_polygon(p,z['points']):
                                    ae=models.AnalyticsEvent(event_type='intrusion',severity='critical' if (settings.sensitivity if settings else 3)>=3 else 'warning',camera=camera_name,sector=sector,description=f"{v['type']} entered restricted zone: {z['name']} (live)",confidence=v['confidence'],frame=0,time_seconds=0,metadata_json=json.dumps({'zone':z['name']}));db.add(ae)
                                    create_alert(db,ae.severity,'Intrusion',ae.description)
                        for f in result['faces']:
                            match=f.get('match','Unknown')
                            if match and match!='Unknown':
                                db.add(models.AnalyticsEvent(event_type='face_match',severity='warning',camera=camera_name,sector=sector,description=f'Recognized profile match: {match} (live)',confidence=f.get('match_confidence',0),frame=0,time_seconds=0,metadata_json=json.dumps({'name':match})))
                                create_alert(db,'warning','Face match',f'{match} recognized on live feed {camera_name}.')
                        for pl in result['plates']:
                            text=(pl.get('text') or '').strip()
                            if text:
                                db.add(models.ANPRRecord(plate=text,camera=camera_name,sector=sector,status='Detected',confidence=int(round(pl.get('confidence',0)*100)),timestamp='Live'))
                                check_watchlist(db,text,camera_name,sector)
                        if summary['is_night'] and (result['vehicles'] or result['faces']):
                            db.add(models.NightEvent(camera=camera_name,sector=sector,description=f"Low-light movement on live feed (brightness {brightness:.1f})",brightness=int(brightness),timestamp='Live'))
                        db.commit()
                        with _lock: _live[camera_id]['last_result']=summary; _live[camera_id]['last_analyzed_at']=now(); _live[camera_id]['error']=None
                    except ModelUnavailableError as e:
                        with _lock: _live[camera_id]['error']=str(e)
                    except Exception as e:
                        with _lock: _live[camera_id]['error']=f'Analysis error: {e}'
                time.sleep(0.05)
    finally:
        cap.release()
        with _lock: _live[camera_id]['running']=False

def _mjpeg_generator(camera_id):
    boundary=b'--frame\r\n'
    while True:
        with _lock:
            st=_live.get(camera_id,{})
            jpg=st.get('latest_jpeg')
            running=st.get('running',False)
        if jpg:
            yield boundary + b'Content-Type: image/jpeg\r\nContent-Length: ' + str(len(jpg)).encode() + b'\r\n\r\n' + jpg + b'\r\n'
        elif not running:
            time.sleep(.25)
        time.sleep(.08)

@app.get('/streams/{camera_id}/mjpeg')
def stream_mjpeg(camera_id:int):
    return StreamingResponse(_mjpeg_generator(camera_id), media_type='multipart/x-mixed-replace; boundary=frame')

@app.post('/streams/{camera_id}/start')
def start_stream(camera_id:int,db:Session=Depends(get_db),_op:str=Depends(require_auth)):
    cam=db.get(models.Camera,camera_id)
    if not cam: raise HTTPException(404,'Camera not found')
    if not cam.rtsp: raise HTTPException(400,'Camera has no RTSP URL')
    with _lock:
        if camera_id in _live and _live[camera_id].get('running'): return {'ok':True,'status':'already_running','camera_id':camera_id}
        stop_event=threading.Event()
        _live[camera_id]={'running':True,'started_at':now(),'rtsp':cam.rtsp,'connected':None,'_stop':stop_event}
    t=threading.Thread(target=_stream_worker,args=(camera_id,cam.rtsp,stop_event),daemon=True); t.start()
    return {'ok':True,'status':'started','camera_id':camera_id,'note':'Opening RTSP feed and running analytics on a timer. Poll /streams/{camera_id}/status.'}
@app.post('/streams/{camera_id}/stop')
def stop_stream(camera_id:int,_op:str=Depends(require_auth)):
    with _lock:
        if camera_id in _live:
            _live[camera_id]['running']=False
            ev=_live[camera_id].get('_stop')
            if ev: ev.set()
    return {'ok':True,'status':'stopped','camera_id':camera_id}
@app.get('/streams/{camera_id}/status')
def stream_status(camera_id:int):
    with _lock:
        st=dict(_live.get(camera_id,{'running':False}))
    st.pop('_stop',None)
    return {'camera_id':camera_id,**st}
@app.post('/assistant/chat', response_model=schemas.AssistantChatResponse)
def assistant_chat(
    payload: schemas.AssistantChatRequest,
    db: Session = Depends(get_db)
):

    cams = db.query(models.Camera).count()
    online = db.query(models.Camera).filter_by(status='Online').count()

    alerts = db.query(models.Alert).order_by(models.Alert.id.desc()).all()
    zones = db.query(models.FenceZone).all()

    # Count alert severity / priority
    alert_levels = {}

    for alert in alerts:
        level = (
            getattr(alert, "severity", None)
            or getattr(alert, "priority", None)
            or "Unknown"
        )

        alert_levels[level] = alert_levels.get(level, 0) + 1

    alert_summary = "\n".join(
        f"- {level} alerts: {count}"
        for level, count in alert_levels.items()
    )

    ev = db.query(models.AnalyticsEvent).count()
    anpr = db.query(models.ANPRRecord).count()
    faces = db.query(models.AnalyticsEvent).filter_by(
        event_type='face_match'
    ).count()
    night = db.query(models.NightEvent).count()
    intrusions = db.query(models.AnalyticsEvent).filter_by(
        event_type='intrusion'
    ).count()

    context = f"""
IBVAP CURRENT SYSTEM STATUS:

Cameras:
- Total cameras: {cams}
- Online cameras: {online}
- Offline cameras: {cams - online}

Alerts:
- Total alerts: {len(alerts)}
- Latest alert: {alerts[0].title if alerts else 'No alerts'}

Alert severity/priority breakdown:
{alert_summary if alert_summary else '- No alert severity data available'}

Analytics:
- Total analytics events: {ev}
- ANPR reads: {anpr}
- Face-match events: {faces}
- Night/low-light events: {night}
- Intrusion events: {intrusions}

Virtual Fence:
- Configured zones: {len(zones)}
"""

    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": """
You are the AI Assistant inside IBVAP
(Intelligent Border Video Analytics Platform).

You assist a border-security operator.

Answer clearly, professionally and concisely.

Use the provided IBVAP system data when answering questions
about cameras, alerts, ANPR, faces, night activity,
intrusions, analytics and fence zones.

Important rules:
- Use only the provided system data for factual system answers.
- Never invent numbers or system events.
- If the requested information is not available in the
  provided data, clearly say that it is not available.
- If the operator asks about offline cameras, calculate:
  total cameras - online cameras.
- If the operator asks about alert severity or priority,
  use the provided severity/priority breakdown.
- Keep responses concise and easy for an operator to understand.
"""
            },
            {
                "role": "user",
                "content": f"""
{context}

Operator question:
{payload.message}
"""
            }
        ]
    )

    reply = response.choices[0].message.content

    return schemas.AssistantChatResponse(reply=reply)

# app/ -> backend/ -> project root -> frontend/
_FRONTEND=os.path.abspath(os.path.join(os.path.dirname(__file__),os.pardir,os.pardir,'frontend'))
if os.path.isdir(_FRONTEND): app.mount('/',StaticFiles(directory=_FRONTEND,html=True),name='frontend')
