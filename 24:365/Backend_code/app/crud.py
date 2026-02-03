from sqlalchemy.orm import Session
from app import models, schemas 

def create_detection(db: Session, detection: schemas.DetectionCreate):
    db_detection = models.Detection(
        ai_server_id=detection.ai_server_id,
        object_type=detection.object_type,
        confidence=detection.confidence,
        location_x=detection.location_x,
        location_y=detection.location_y,
        
        is_fire_detected=detection.is_fire_detected,
        is_smoke_detected=detection.is_smoke_detected         
    )

    db.add(db_detection)
    db.commit() 
    db.refresh(db_detection)
    return db_detection
