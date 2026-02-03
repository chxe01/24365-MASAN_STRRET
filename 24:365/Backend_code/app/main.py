import asyncio
import logging
from typing import List, Dict
import cv2
import numpy as np
import time
import json
from datetime import datetime, date
from threading import Thread

import mysql.connector 

from fastapi import FastAPI, WebSocket, Request, Response, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import run as uvicorn_run

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
}
TABLE_NAME = "detection"

MAX_LOG_ENTRIES = 100000

DB_SAVE_INTERVAL = 10
last_db_save_time: Dict[str, float] = {}

try:
    __app_id = __app_id
    __firebase_config = json.loads(__firebase_config)
except NameError:
    __app_id = "default-ai-app"
    __firebase_config = {"apiKey": "local-key", "authDomain": "local-auth", "projectId": "local-project"}

AI_SERVER_ID = "24365"

websocket_clients = set()
camera = None
event_loop = None

def create_connection():
    try:
        cnx = mysql.connector.connect(**DB_CONFIG, use_pure=True)
        return cnx
    except mysql.connector.Error as err:
        print(f"ERROR: MySQL 연결 오류 발생: {err}")
        return None

def check_db_and_create_table():
    cnx = create_connection()
    if not cnx:
        print("경고: 데이터베이스 연결에 실패하여 DB 로깅 기능이 비활성화됩니다.")
        return False
    
    cursor = cnx.cursor()
    
    try:
        cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        cnx.commit()
    except mysql.connector.Error as err:
        print(f"{err}")
        
    create_table_sql = f"""
        CREATE TABLE {TABLE_NAME} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME NOT NULL,
            ai_server_id VARCHAR(50) NOT NULL,
            class_name VARCHAR(50) NOT NULL,
            confidence DECIMAL(4, 3) NOT NULL,
            is_fire_detected BOOLEAN,
            is_smoke_detected BOOLEAN,
            location_x DECIMAL(5, 4) NULL,
            location_y DECIMAL(5, 4) NULL,
            box_width DECIMAL(5, 4) NULL,
            box_height DECIMAL(5, 4) NULL
        )
    """
    
    try:
        cursor.execute(create_table_sql)
        cnx.commit()
        return True
    except mysql.connector.Error as err:
        print(f"ERROR: MySQL 테이블 생성 오류: {err}")
        return False
    finally:
        cursor.close()
        cnx.close()

def manage_log_limit(cnx):
    cursor = cnx.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        count = cursor.fetchone()[0]
        
        if count > MAX_LOG_ENTRIES:
            delete_count = count - MAX_LOG_ENTRIES
            
            delete_sql = f"""
                DELETE FROM {TABLE_NAME} 
                ORDER BY id ASC 
                LIMIT {delete_count}
            """
            cursor.execute(delete_sql)
            cnx.commit()
            
    except mysql.connector.Error as err:
        print(f"ERROR: 로그 제한 관리 오류: {err}")
        cnx.rollback()
    except Exception as e:
        print(f"ERROR: 예상치 못한 로그 관리 오류: {e}")
    finally:
        cursor.close()

def log_to_mysql(data: dict):
    cnx = create_connection()
    if not cnx:
        return

    cursor = cnx.cursor()
    
    sql = f"""
        INSERT INTO {TABLE_NAME} 
        (timestamp, ai_server_id, class_name, confidence, is_fire_detected, is_smoke_detected, location_x, location_y, box_width, box_height)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    detection_time = datetime.now()
    if 'timestamp' in data:
        try:
            detection_time = datetime.fromisoformat(data['timestamp'])
        except (ValueError, TypeError):
            pass

    class_name = data.get("class_name", "UNKNOWN").upper()
    is_fire = data.get("is_fire_detected", False) or class_name == 'FIRE'
    is_smoke = data.get("is_smoke_detected", False) or class_name == 'SMOKE'
    confidence = data.get("confidence", 0.0)

    def safe_float(key):
        val = data.get(key)
        try:
            return float(val) if val is not None else None
        except ValueError:
            return None
            
    log_data = (
        detection_time,
        data.get("ai_server_id", AI_SERVER_ID),
        class_name,
        confidence,
        is_fire,
        is_smoke,
        safe_float("location_x"),
        safe_float("location_y"),
        safe_float("box_width"),
        safe_float("box_height")
    )

    try:
        cursor.execute(sql, log_data)
        cnx.commit()
        
        manage_log_limit(cnx) 

    except mysql.connector.Error as err:
        print(f"ERROR: MySQL 데이터 삽입 오류: {err}")
        print("🚨🚨🚨 DB 테이블의 컬럼이 누락되었거나 이름이 잘못되었을 수 있습니다. DB 스키마를 확인하세요. 🚨🚨🚨")
        cnx.rollback()
    except Exception as e:
        print(f"ERROR: 예상치 못한 데이터 삽입 오류: {e}")
    finally:
        cursor.close()
        cnx.close()
        

def get_camera():
    global camera
    if camera is None:
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            print("ERROR: 웹캠을 열 수 없습니다. 더미 프레임을 사용합니다.")
            camera = 'dummy'
    return camera

def dummy_frame():
    text = "Camera Unavailable"
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    text_size = cv2.getTextSize(text, font, 1.5, 3)[0]
    text_x = (frame.shape[1] - text_size[0]) // 2
    text_y = (frame.shape[0] + text_size[1]) // 2
    
    cv2.putText(frame, text, (text_x, text_y), font, 1.5, (0, 0, 255), 3, cv2.LINE_AA)
    
    return frame

async def broadcast_detection(message: str):
    for client in list(websocket_clients):
        try:
            await client.send_text(message)
        except WebSocketDisconnect:
            websocket_clients.remove(client)
        except RuntimeError as e:
            pass
        except Exception as e:
            print(f"Error sending message to client: {e}")
            try:
                websocket_clients.remove(client)
            except KeyError:
                pass


def simulate_yolo_detection():
    CLASSES = [
        {"name": "FIRE", "color": (0, 0, 255)}, 
        {"name": "SMOKE", "color": (0, 165, 255)},
    ]
    
    try:
        current_loop = asyncio.get_event_loop()
    except RuntimeError:
        current_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(current_loop)


    while True:
        try:
            if np.random.rand() < 0.15: 
                detection_class = np.random.choice(CLASSES)
                class_name = detection_class["name"]
                confidence = round(np.random.uniform(0.65, 0.98), 2)
                
                box_width = round(np.random.uniform(0.1, 0.3), 2)
                box_height = round(np.random.uniform(0.1, 0.3), 2)
                location_x = round(np.random.uniform(0.1, 0.9), 2)
                location_y = round(np.random.uniform(0.1, 0.9), 2)
                
                is_fire = (class_name == "FIRE")
                is_smoke = (class_name == "SMOKE")
                
                detection_data = {
                    "timestamp": datetime.now().isoformat(),
                    "ai_server_id": AI_SERVER_ID,
                    "class_name": class_name, 
                    "confidence": confidence,
                    "is_fire_detected": is_fire,
                    "is_smoke_detected": is_smoke,
                    "location_x": location_x, 
                    "location_y": location_y,
                    "box_width": box_width,
                    "box_height": box_height,
                }
                
                message = json.dumps(detection_data)
                
                current_time = time.time()
                ai_server_id_sim = detection_data.get("ai_server_id", AI_SERVER_ID)
                last_save_time_sim = last_db_save_time.get(ai_server_id_sim, 0.0)

                if current_time - last_save_time_sim >= DB_SAVE_INTERVAL:
                    print(f"INFO: Sim log skipped (DB save disabled for testing).")

                if current_loop.is_running():
                    asyncio.run_coroutine_threadsafe(broadcast_detection(message), current_loop)
                
            time.sleep(0.2) 
            
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                break
            print(f"WebSocket Simulation RuntimeError: {e}")
            time.sleep(1)
        except Exception as e:
            print(f"Unexpected Simulation Error: {e}")
            time.sleep(1)

detection_thread = Thread(target=simulate_yolo_detection)
detection_thread.daemon = True
detection_thread.start()


app = FastAPI()

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    global event_loop
    event_loop = asyncio.get_event_loop()
    check_db_and_create_table()


app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", response_class=FileResponse)
async def get_home():
    return FileResponse("home.html") 


@app.post("/detections/")
async def receive_detection_data(detection_data: dict):
    
    ai_server_id = detection_data.get("ai_server_id", AI_SERVER_ID)
    if "ai_server_id" not in detection_data:
        detection_data["ai_server_id"] = ai_server_id 

    global last_db_save_time
    current_time = time.time()
    last_save_time = last_db_save_time.get(ai_server_id, 0.0)

    if current_time - last_save_time >= DB_SAVE_INTERVAL:
        log_to_mysql(detection_data)
        last_db_save_time[ai_server_id] = current_time
        print(f"RECEIVED HTTP POST and DB SAVED: {detection_data.get('class_name')}. Next save in {DB_SAVE_INTERVAL}s.")
    else:
        print(f"RECEIVED HTTP POST but DB SAVE SKIPPED (Interval not met): {detection_data.get('class_name')}")
    
    message = json.dumps(detection_data)
    
    await broadcast_detection(message)
    
    return {"status": "success", "message": "Detection received and broadcasted."}


@app.get("/get_today_counts") 
async def get_today_counts():
    cnx = create_connection()
    if not cnx:
        return {"status": "error", "message": "Database connection failed."}

    cursor = cnx.cursor()
    
    try:
        fire_sql = f"""
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE is_fire_detected = TRUE 
            AND DATE(timestamp) = CURDATE()
        """
        cursor.execute(fire_sql)
        fire_count = cursor.fetchone()[0]

        smoke_sql = f"""
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE is_smoke_detected = TRUE
            AND DATE(timestamp) = CURDATE()
        """
        cursor.execute(smoke_sql)
        smoke_count = cursor.fetchone()[0]

        return {
            "status": "success", 
            "data": {
                "fire_count": fire_count,
                "smoke_count": smoke_count
            }
        }
        
    except mysql.connector.Error as err:
        print(f"ERROR: MySQL 통계 조회 오류: {err}")
        return {"status": "error", "message": f"Statistics retrieval failed: {err}"}
    finally:
        cursor.close()
        cnx.close()


@app.get("/get_logs/")
async def get_filtered_logs():
    cnx = create_connection()
    if not cnx:
        return {"status": "error", "message": "Database connection failed."}

    cursor = cnx.cursor(dictionary=True)
    
    sql = f"""
        SELECT * FROM {TABLE_NAME}
        WHERE is_fire_detected = TRUE OR is_smoke_detected = TRUE
        ORDER BY timestamp DESC
        LIMIT 100
    """
    
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        
        for row in results:
            if isinstance(row.get('timestamp'), datetime):
                row['timestamp'] = row['timestamp'].isoformat()
                
        return {"status": "success", "data": results}
        
    except mysql.connector.Error as err:
        print(f"ERROR: MySQL 로그 조회 오류: {err}")
        return {"status": "error", "message": f"Log retrieval failed: {err}"}
    finally:
        cursor.close()
        cnx.close()


def generate_video_frames():
    camera = get_camera()
    
    while True:
        if camera == 'dummy':
            frame = dummy_frame()
        else:
            success, frame = camera.read()
            if not success:
                frame = dummy_frame()
            else:
                pass
        
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        time.sleep(1/30) 

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_video_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws/detections")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.add(websocket)
    print("WebSocket Connected")
    try:
        while True:
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
        print("WebSocket Disconnected")
    except Exception as e:
        print(f"WebSocket Error: {e}")
        try:
            websocket_clients.remove(websocket)
        except KeyError:
            pass

if __name__ == "__main__":
    print("\n--- AI 비디오 스트리밍/감지 서버 시작 ---")
    print(f"루트 (비디오 테스트): http://127.0.0.1:9000/")
    print(f"감지 로그 GET API: http://127.0.0.1:9000/get_logs/")
    print(f"오늘 통계 GET API: http://127.0.0.1:9000/get_today_counts")
    
    try:
        uvicorn_run(app, host="0.0.0.0", port=9000)
    except Exception as e:
        print(f"서버 실행 중 오류 발생: {e}")