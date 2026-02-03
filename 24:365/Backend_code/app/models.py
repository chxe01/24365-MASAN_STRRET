from pydantic import BaseModel

class DetectionData(BaseModel):
    ai_server_id: str
    object_type: str
    confidence: float
    location_x: float = 0.0
    location_y: float = 0.0
    is_fire_detected: bool = False
    is_smoke_detected: bool = False