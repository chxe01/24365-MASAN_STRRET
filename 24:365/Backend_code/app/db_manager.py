import sqlite3
from typing import List, Dict, Any

DATABASE_NAME = "detections.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            class_name TEXT NOT NULL,
            confidence REAL
        )
    """)
    conn.commit()
    conn.close()

def save_detection_data(timestamp: str, detections: List[Dict[str, Any]]):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for det in detections:
        class_name = det.get('class_name')
        confidence = det.get('confidence')
        
        if class_name:
            cursor.execute(
                "INSERT INTO events (timestamp, class_name, confidence) VALUES (?, ?, ?)",
                (timestamp, class_name, confidence)
            )
            
    conn.commit()
    conn.close()
    print(f"🟢🟢 DB SUCCESS: {len(detections)}개의 감지 데이터 저장 완료.") 

init_db()