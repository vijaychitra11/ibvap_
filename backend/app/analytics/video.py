import cv2, json, time
from pathlib import Path
from typing import Any
from .detection import detect_frame, models_status
from .tracker import CentroidTracker
from .fence import inside_polygon, centroid

def analyze_video(video_path, sample_every=10, max_frames=600, fence_polygons=None, face_profiles=None, sensitivity=3):
    cap=cv2.VideoCapture(video_path)
    if not cap.isOpened(): raise ValueError('Could not open uploaded video')
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 0); total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0); w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0); h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration=total/fps if fps else 0; tracker=CentroidTracker(); counts={}; detections=[]; plates=[]; faces=[]; low=0; intrusions=[]; loiter={}; sampled=0; idx=0; events=[]; zone_state={}; zone_entries={}
    try:
        while True:
            ok,frame=cap.read()
            if not ok: break
            if idx%sample_every: idx+=1; continue
            sampled+=1
            if sampled>max_frames: break
            gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY); brightness=float(gray.mean()); is_low=brightness<55
            if is_low: low+=1
            result=detect_frame(frame,require_plate=False,face_profiles=face_profiles)
            for v in result['vehicles']:
                counts[v['type']]=counts.get(v['type'],0)+1
                detections.append({'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'type':v['type'],'confidence':v['confidence'],'box':v['box'],'is_human':v.get('is_human',False)})
            tracked=tracker.update(result['vehicles'])
            for tid,v in tracked:
                p=centroid(v['box']); inside=[]
                for z in fence_polygons or []:
                    if z.get('enabled',True) and inside_polygon(p,z.get('points',[])): inside.append(z['name'])
                if inside:
                    intrusions.append({'track_id':tid,'zones':inside,'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'object':v['type'],'box':v['box']})
                    events.append({'type':'intrusion','severity':'critical' if sensitivity>=3 else 'warning','confidence':v['confidence'],'description':f"{v['type']} entered restricted zone: {', '.join(inside)}",'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'metadata':{'track_id':tid,'zones':inside}})
                    was_inside=zone_state.get(tid,False)
                    if not was_inside:
                        zone_entries[tid]=zone_entries.get(tid,0)+1
                        if zone_entries[tid]>=3:
                            events.append({'type':'suspicious_activity','severity':'critical','confidence':v['confidence'],'description':f"Track {tid} re-entered restricted zone {zone_entries[tid]}x — possible probing behavior",'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'metadata':{'track_id':tid,'entries':zone_entries[tid]}})
                    zone_state[tid]=True
                else:
                    zone_state[tid]=False
                key=(tid,idx//max(sample_every,1))
                loiter[tid]=loiter.get(tid,0)+1
                if loiter[tid]>=max(8,20-sensitivity*4):
                    events.append({'type':'loitering','severity':'warning','confidence':v['confidence'],'description':f"Track {tid} remained in view for an extended period",'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'metadata':{'track_id':tid}})
                    loiter[tid]=-10**6
            for p in result['plates']:
                plates.append({'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,**p})
            for f in result['faces']:
                faces.append({'frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,**f})
                match=f.get('match','Unknown')
                if match and match!='Unknown':
                    events.append({'type':'face_match','severity':'warning','confidence':f.get('match_confidence',0),'description':f'Recognized profile match: {match}','frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'metadata':{'name':match}})
                elif face_profiles:
                    events.append({'type':'face_detected','severity':'info','confidence':f.get('confidence',0),'description':'Unrecognized face detected','frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'metadata':{}})
            if is_low and (result['vehicles'] or result['faces']):
                events.append({'type':'night_movement','severity':'warning','confidence':0.75,'description':f'Low-light movement detected (brightness {brightness:.1f})','frame':idx,'time_seconds':round(idx/fps,2) if fps else 0,'metadata':{'brightness':round(brightness,1),'objects':len(result['vehicles']),'faces':len(result['faces'])}})
            idx+=1
    finally: cap.release()
    # dedupe adjacent repeated events for a usable alert feed
    compact=[]; seen=set()
    for e in events:
        k=(e['type'],e['description'],round(e['time_seconds']/5))
        if k not in seen: seen.add(k); compact.append(e)
    return {'video':{'filename':Path(video_path).name,'fps':round(fps,2),'total_frames':total,'duration_seconds':round(duration,2),'resolution':f'{w}x{h}'},'analysis':{'frames_analyzed':sampled,'sample_every_frames':sample_every,'vehicle_counts':counts,'vehicle_detections':detections,'sample_interval_seconds':round(sample_every/fps,3) if fps else 0,'plate_detections':plates,'face_detections':faces,'low_light_frames':low,'intrusions':intrusions,'events':compact},'model_status':models_status()}
