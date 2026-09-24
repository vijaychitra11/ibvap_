import json, cv2

def inside_polygon(point, polygon):
    if len(polygon)<3: return False
    contour=cv2.UMat if False else None
    x,y=point; inside=False
    j=len(polygon)-1
    for i in range(len(polygon)):
        xi,yi=polygon[i]; xj,yj=polygon[j]
        hit=((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/(yj-yi+1e-9)+xi)
        if hit: inside=not inside
        j=i
    return inside

def centroid(box):
    x1,y1,x2,y2=box; return ((x1+x2)/2,(y1+y2)/2)
