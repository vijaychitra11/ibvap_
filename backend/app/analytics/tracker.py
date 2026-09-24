import math
class CentroidTracker:
    def __init__(self,max_distance=90,max_missing=12):
        self.next_id=1; self.objects={}; self.missing={}; self.max_distance=max_distance; self.max_missing=max_missing
    def update(self,detections):
        centers=[((d['box'][0]+d['box'][2])/2,(d['box'][1]+d['box'][3])/2) for d in detections]
        assigned=set(); result=[]
        for i,c in enumerate(centers):
            best=None; bd=self.max_distance
            for oid,old in self.objects.items():
                if oid in assigned: continue
                dist=math.hypot(c[0]-old[0],c[1]-old[1])
                if dist<bd: bd=dist; best=oid
            if best is None: best=self.next_id; self.next_id+=1
            self.objects[best]=c; self.missing[best]=0; assigned.add(best)
            result.append((best,detections[i]))
        for oid in list(self.objects):
            if oid not in assigned:
                self.missing[oid]=self.missing.get(oid,0)+1
                if self.missing[oid]>self.max_missing:
                    self.objects.pop(oid,None); self.missing.pop(oid,None)
        return result
