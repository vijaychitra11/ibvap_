import os, re
from pathlib import Path
from typing import Any
import cv2
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None
from .ocr import read_plate
from .face import detect_faces, match_faces
from ..config import CONFIDENCE, PLATE_MODEL, VEHICLE_MODEL

# app/ now lives under backend/, so: analytics -> app -> backend -> project root.
BACKEND_DIR=Path(__file__).resolve().parents[2]
BASE_DIR=BACKEND_DIR.parent
_vehicle_model=None; _plate_model=None; _vehicle_error=None; _plate_error=None
class ModelUnavailableError(RuntimeError): pass

def _resolve(value, default):
    p=Path(value or default)
    if p.is_absolute(): return p
    # Prefer <project-root>/models/... (as documented), fall back to backend/models/...
    root_path=BASE_DIR/p
    return root_path if root_path.exists() else (BACKEND_DIR/p if (BACKEND_DIR/p).exists() else root_path)

def _load_models():
    global _vehicle_model,_plate_model,_vehicle_error,_plate_error
    if YOLO is None:
        _vehicle_error = 'ultralytics is not installed. Run: python -m pip install ultralytics'
        _plate_error = 'ultralytics is not installed. Run: python -m pip install ultralytics'
        return
    if _vehicle_model is None and _vehicle_error is None:
        p=_resolve(VEHICLE_MODEL,'models/vehicle.pt')
        try:
            fallback=BACKEND_DIR/'yolo11n.pt'
            _vehicle_model=YOLO(str(p if p.exists() else fallback if fallback.exists() else 'yolo11n.pt'))
        except Exception as e: _vehicle_error=str(e)
    if _plate_model is None and _plate_error is None:
        p=_resolve(PLATE_MODEL,'models/plate.pt')
        try: _plate_model=YOLO(str(p)) if p.exists() else None
        except Exception as e: _plate_error=str(e)
        if _plate_model is None and not _plate_error: _plate_error=f'License-plate model not found: {p}'

def models_status():
    _load_models()
    return {'vehicle_model':{'loaded':_vehicle_model is not None,'error':_vehicle_error},'plate_model':{'loaded':_plate_model is not None,'error':_plate_error},'ocr':{'configured':bool(os.getenv('TESSERACT_CMD')),'engine':'tesseract'}}

def _box(b,w,h):
    x1,y1,x2,y2=map(int,b); return [max(0,min(x1,w-1)),max(0,min(y1,h-1)),max(0,min(x2,w)),max(0,min(y2,h))]

def _class_name(model, cls): return str(model.names.get(cls,cls) if hasattr(model.names,'get') else model.names[cls])

def _fallback_plate_regions(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY); blur=cv2.bilateralFilter(gray,9,75,75); edges=cv2.Canny(blur,70,180)
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE); h,w=gray.shape; out=[]
    for c in sorted(contours,key=cv2.contourArea,reverse=True)[:80]:
        x,y,ww,hh=cv2.boundingRect(c); ratio=ww/max(hh,1); area=ww*hh
        if 2.0<=ratio<=7.0 and area>500 and area<0.15*w*h:
            crop=image[y:y+hh,x:x+ww]
            try: text=read_plate(crop)
            except Exception: text=''
            if text: out.append({'text':re.sub(r'[^A-Z0-9 -]','',text.upper()),'confidence':0.35,'box':[x,y,x+ww,y+hh],'method':'opencv-fallback'})
            if len(out)>=5: break
    return out

def detect_image(image_path, require_plate=True, face_profiles=None):
    image=cv2.imread(str(image_path))
    if image is None: raise ValueError(f'Could not read image: {image_path}')
    return detect_frame(image, require_plate=require_plate, face_profiles=face_profiles)

def detect_frame(image, require_plate=True, face_profiles=None):
    """Same pipeline as detect_image but takes an in-memory BGR ndarray directly —
    avoids a disk round-trip for video/live-stream frames."""
    _load_models()
    if _vehicle_model is None: raise ModelUnavailableError(f'Vehicle model unavailable: {_vehicle_error or "unknown error"}')
    if require_plate and _plate_model is None: raise ModelUnavailableError(f'License-plate model unavailable: {_plate_error or "unknown error"}')
    h,w=image.shape[:2]; vehicles=[]
    for r in _vehicle_model(image,conf=CONFIDENCE,verbose=False):
        for b in r.boxes:
            cls=int(b.cls[0]); conf=float(b.conf[0]); name=_class_name(_vehicle_model,cls)
            if name.lower() not in {'person','car','motorcycle','bus','truck','bicycle','van','suv'} and name.lower() not in {'bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe'}: continue
            vehicles.append({'type':name,'confidence':round(conf,3),'box':_box(b.xyxy[0],w,h),'is_human':name.lower()=='person'})
    plates=[]
    if _plate_model is not None:
        for r in _plate_model(image,conf=max(.25,CONFIDENCE),verbose=False):
            for b in r.boxes:
                x1,y1,x2,y2=_box(b.xyxy[0],w,h); crop=image[y1:y2,x1:x2]
                if crop.size==0: continue
                try: text=read_plate(crop)
                except Exception: text=''
                plates.append({'text':text,'confidence':round(float(b.conf[0]),3),'box':[x1,y1,x2,y2],'method':'plate-model'})
    elif not require_plate:
        plates=_fallback_plate_regions(image)
    faces=detect_faces(image); profiles=face_profiles or []
    if profiles: faces=match_faces(faces,profiles)
    else:
        for f in faces: f.pop('embedding',None); f['match']='Unknown'; f['match_confidence']=0.0
    return {'vehicles':vehicles,'plates':plates,'faces':faces}
