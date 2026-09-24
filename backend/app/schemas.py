from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

class CameraBase(BaseModel):
    name: str; sector: str; ip: str; rtsp: str=''; type: str='Fixed IP'; status: str='Online'; img: str=''; night: bool=False
class CameraCreate(CameraBase): pass
class CameraOut(CameraBase):
    model_config=ConfigDict(from_attributes=True); id:int
class AlertBase(BaseModel): severity:str; title:str; description:str=''
class AlertCreate(AlertBase): pass
class AlertOut(AlertBase):
    model_config=ConfigDict(from_attributes=True); id:int; ref_code:str; timestamp:str
class FenceZoneBase(BaseModel): name:str; status:str='teal'
class FenceZoneCreate(FenceZoneBase): pass
class FenceZoneOut(FenceZoneBase):
    model_config=ConfigDict(from_attributes=True); id:int
class FenceSettingsUpdate(BaseModel):
    sensitivity:Optional[int]=Field(None, ge=1, le=3); human_detection:Optional[bool]=None; animal_filter:Optional[bool]=None; directional_alert:Optional[bool]=None; armed:Optional[bool]=None
class FenceSettingsOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); sensitivity:int; human_detection:bool; animal_filter:bool; directional_alert:bool; armed:bool
class LoginRequest(BaseModel): operator_id:str; passcode:str
class LoginResponse(BaseModel): ok:bool; operator_id:str; token:str
class AssistantChatRequest(BaseModel): message:str
class AssistantChatResponse(BaseModel): reply:str
class ANPRRecordOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:int; plate:str; camera:str=''; sector:str=''; vehicle_type:str=''; status:str; confidence:int; timestamp:str
class NightEventOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:int; camera:str=''; sector:str=''; description:str; brightness:int; timestamp:str
class ModelsStatusOut(BaseModel): vehicle_model:dict; plate_model:dict; ocr:dict
class FencePolygonCreate(BaseModel): name:str; camera:str=''; sector:str=''; points:List[List[float]]; enabled:bool=True
class FencePolygonOut(FencePolygonCreate):
    model_config=ConfigDict(from_attributes=True); id:int
class WatchlistPlateCreate(BaseModel): plate:str; label:str='Watchlist'; active:bool=True
class WatchlistPlateOut(WatchlistPlateCreate):
    model_config=ConfigDict(from_attributes=True); id:int
class FaceProfileCreate(BaseModel): name:str; embedding:List[float]; active:bool=True
class FaceProfileOut(BaseModel):
    id:int; name:str; active:bool
class AnalyticsEventOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:int; event_type:str; severity:str; camera:str=''; sector:str=''; description:str=''; confidence:float; frame:int; time_seconds:float; metadata_json:str='{}'; created_at:Any
class JobOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:int; source:str; camera:str; sector:str; status:str; progress:float; result_json:str; error:str; created_at:Any
