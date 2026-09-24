import cv2, json, math
from typing import List, Tuple

CASCADE = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
_cascade = cv2.CascadeClassifier(CASCADE)

def embedding(face_bgr):
    gray=cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    gray=cv2.resize(gray,(32,32)).astype('float32')/255.0
    v=gray.flatten(); n=float((v*v).sum())**0.5 or 1.0
    return (v/n).tolist()

def detect_faces(image_bgr):
    gray=cv2.cvtColor(image_bgr,cv2.COLOR_BGR2GRAY)
    faces=_cascade.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=5,minSize=(40,40))
    out=[]
    for x,y,w,h in faces:
        crop=image_bgr[y:y+h,x:x+w]
        out.append({'box':[int(x),int(y),int(x+w),int(y+h)],'confidence':0.70,'embedding':embedding(crop)})
    return out

def cosine(a,b):
    if not a or not b or len(a)!=len(b): return -1.0
    return sum(x*y for x,y in zip(a,b))

def match_faces(detections, profiles, threshold=0.82):
    for d in detections:
        best=None; best_score=-1
        for p in profiles:
            score=cosine(d['embedding'],p['embedding'])
            if score>best_score: best_score=score; best=p
        d['match']=best['name'] if best and best_score>=threshold else 'Unknown'
        d['match_confidence']=round(max(0,best_score),3)
        d.pop('embedding',None)
    return detections
