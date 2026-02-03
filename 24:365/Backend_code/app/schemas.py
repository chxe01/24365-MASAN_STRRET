from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class DetectionCreate(BaseModel):
    ai_server_id: str = Field(..., description="데이터를 보낸 AI 서버의 고유 ID")
    object_type: str = Field(..., description="감지된 객체의 종류 (예: 'car', 'person')")
    confidence: float = Field(..., ge=0.0, le=1.0, description="감지 신뢰도 (0.0 ~ 1.0)")
    location_x: float
    location_y: float
    is_fire_detected: bool
    is_smoke_detected: bool

class Detection(DetectionCreate):
    id: int
    detection_time: datetime

    class Config:
        orm_mode = True


from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class DetectionCreate(BaseModel):
    ai_server_id: str = Field(..., description="데이터를 보낸 AI 서버의 고유 ID")
    object_type: str = Field(..., description="감지된 객체의 종류")
    confidence: float = Field(..., ge=0.0, le=1.0, description="감지 신뢰도 (0.0 ~ 1.0)")
    location_x: float
    location_y: float
    is_fire_detected: bool = Field(default=False, description="산불 모델 감지 결과")
    is_smoke_detected: bool = Field(default=False, description="연기 모델 감지 결과")



class Detection(DetectionCreate):
    id: int
    detection_time: datetime

    class Config:
        orm_mode = True 