from .models import Camera, Alert, FenceZone, FenceSettings

CAMERAS = [
    dict(name="BOP-12 North", sector="Sector A-3", ip="192.168.1.12", type="Thermal",
         status="Online", night=True,
         img="https://images.unsplash.com/photo-1519681393784-d120267933ba?w=800&q=68",
         rtsp="rtsp://192.168.1.12:554/stream1"),
    dict(name="BOP-04 Ridge", sector="Sector B-1", ip="192.168.1.04", type="PTZ",
         status="Online", night=False,
         img="https://images.unsplash.com/photo-1470770903676-69b98201ea1c?w=800&q=68",
         rtsp="rtsp://192.168.1.04:554/stream1"),
    dict(name="Gate Alpha (Checkpoint)", sector="Zone North-East", ip="192.168.1.21", type="Fixed IP",
         status="Online", night=False,
         img="https://images.unsplash.com/photo-1615729947596-a598e5de0ab3?w=800&q=68",
         rtsp="rtsp://192.168.1.21:554/stream1"),
    dict(name="Checkpoint Delta", sector="Sector A-3", ip="192.168.1.33", type="Dome",
         status="Offline", night=True,
         img="https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=800&q=68",
         rtsp="rtsp://192.168.1.33:554/stream1"),
    dict(name="Creek Bed Cam", sector="Sector B-1", ip="192.168.1.45", type="Fixed IP",
         status="Online", night=False,
         img="https://images.unsplash.com/photo-1486870591958-9b9d0d1dda99?w=800&q=68",
         rtsp="rtsp://192.168.1.45:554/stream1"),
]

ALERTS = [
    dict(ref_code="#AL-9921", severity="critical", title="Multiple Heat Signatures Detected",
         description="Sector 7G, Northern Ridge. Thermal optics confirm 3 bipedal targets traversing restricted zone.",
         timestamp="03:42:11 Z · Today"),
    dict(ref_code="#AL-9920", severity="warning", title="Unregistered Vehicle Approach",
         description="ANPR match failure at Checkpoint Alpha. Vehicle proceeding at 40km/h towards perimeter wire.",
         timestamp="02:15:00 Z · Today"),
    dict(ref_code="#AL-9919", severity="info", title="Camera Feed Restored",
         description="PTZ-04 connection re-established after brief weather-related dropout.",
         timestamp="01:05:44 Z · Today"),
    dict(ref_code="#AL-9918", severity="warning", title="Facial Recognition Anomaly",
         description="Subject at Gate B does not match credential biometric profile. Detention recommended.",
         timestamp="23:50:12 Z · Yesterday"),
    dict(ref_code="#AL-9916", severity="critical", title="Seismic Sensor Triggered",
         description="Heavy vibration detected at Outpost Delta. Possible subterranean activity.",
         timestamp="19:33:45 Z · Yesterday"),
]

ZONES = [
    dict(name="Zone A — North Perimeter", status="amber"),
    dict(name="Zone B — Creek Bed", status="teal"),
    dict(name="Zone C — Ridge Access Road", status="teal"),
]


def seed_if_empty(db):
    if db.query(Camera).count() == 0:
        db.bulk_save_objects([Camera(**c) for c in CAMERAS])
    if db.query(Alert).count() == 0:
        db.bulk_save_objects([Alert(**a) for a in ALERTS])
    if db.query(FenceZone).count() == 0:
        db.bulk_save_objects([FenceZone(**z) for z in ZONES])
    if db.query(FenceSettings).count() == 0:
        db.add(FenceSettings(sensitivity=3, human_detection=True, animal_filter=True,
                              directional_alert=False, armed=False))
    db.commit()
