from sqlalchemy import Column, Integer, String, Boolean, Text, Float, DateTime
from datetime import datetime
from .database import Base

class Camera(Base):
    __tablename__ = 'cameras'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    sector = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    rtsp = Column(String, default='')
    type = Column(String, default='Fixed IP')
    status = Column(String, default='Online')
    img = Column(String, default='')
    night = Column(Boolean, default=False)

class Alert(Base):
    __tablename__ = 'alerts'
    id = Column(Integer, primary_key=True, index=True)
    ref_code = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, default='')
    timestamp = Column(String, default='')

class FenceZone(Base):
    __tablename__ = 'fence_zones'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default='teal')

class FenceSettings(Base):
    __tablename__ = 'fence_settings'
    id = Column(Integer, primary_key=True, index=True)
    sensitivity = Column(Integer, default=3)
    human_detection = Column(Boolean, default=True)
    animal_filter = Column(Boolean, default=True)
    directional_alert = Column(Boolean, default=False)
    armed = Column(Boolean, default=False)

class ANPRRecord(Base):
    __tablename__ = 'anpr_records'
    id = Column(Integer, primary_key=True, index=True)
    plate = Column(String, nullable=False)
    camera = Column(String, default='')
    sector = Column(String, default='')
    vehicle_type = Column(String, default='')
    status = Column(String, nullable=False, default='Detected')
    confidence = Column(Integer, default=0)
    timestamp = Column(String, default='')

class NightEvent(Base):
    __tablename__ = 'night_events'
    id = Column(Integer, primary_key=True, index=True)
    camera = Column(String, default='')
    sector = Column(String, default='')
    description = Column(String, nullable=False)
    brightness = Column(Integer, default=0)
    timestamp = Column(String, default='')

class AnalyticsEvent(Base):
    __tablename__ = 'analytics_events'
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    severity = Column(String, default='info')
    camera = Column(String, default='')
    sector = Column(String, default='')
    description = Column(Text, default='')
    confidence = Column(Float, default=0.0)
    frame = Column(Integer, default=0)
    time_seconds = Column(Float, default=0.0)
    metadata_json = Column(Text, default='{}')
    created_at = Column(DateTime, default=datetime.utcnow)

class FencePolygon(Base):
    __tablename__ = 'fence_polygons'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    camera = Column(String, default='')
    sector = Column(String, default='')
    points_json = Column(Text, nullable=False, default='[]')
    enabled = Column(Boolean, default=True)

class WatchlistPlate(Base):
    __tablename__ = 'watchlist_plates'
    id = Column(Integer, primary_key=True, index=True)
    plate = Column(String, unique=True, nullable=False)
    label = Column(String, default='Watchlist')
    active = Column(Boolean, default=True)

class FaceProfile(Base):
    __tablename__ = 'face_profiles'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    embedding_json = Column(Text, nullable=False)
    active = Column(Boolean, default=True)

class ProcessingJob(Base):
    __tablename__ = 'processing_jobs'
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, default='')
    camera = Column(String, default='')
    sector = Column(String, default='')
    status = Column(String, default='queued')
    progress = Column(Float, default=0.0)
    result_json = Column(Text, default='{}')
    error = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
