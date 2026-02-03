import requests
import json
import time
import cv2 
from ultralytics import YOLO 
import sys 
import os
import random 
import numpy as np

FASTAPI_ENDPOINT = "http://127.0.0.1:9000/detections/" 
AI_SERVER_ID = "24/365" 

FIRE_CLASS_NAMES = ['fire'] 
SMOKE_CLASS_NAMES = ['smoke'] 

SUBMISSION_INTERVAL = 10
next_submission_time = time.time() + SUBMISSION_INTERVAL 


if __name__ == "__main__":
    print("--- 🔥 최종 진단 시작: YOLO 감지 상세 로그 확인 ---")
    print(f"--- 🚨 현재 설정된 Fire 클래스 이름: {FIRE_CLASS_NAMES} ---")

    MODEL_PATH = 'best24365.pt'
    model = None 

    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        print(f"❌ YOLO 모델 로드 실패. 파일 경로 ({MODEL_PATH})를 확인하세요.")
        print("💡 모델 파일이 없으므로, 데이터 전송 테스트만 진행합니다.")

    source = 0
    
    if model is None:
        def mock_results_generator():
            mock_class_map = {0: 'fire', 1: 'smoke', 2: 'person'}
            while True:
                mock_cls_id = random.choice([0, 1, 1, 1, 2, 2, 2, 2, 2, 2])
                mock_cls = mock_class_map[mock_cls_id]
                mock_conf = random.uniform(0.7, 0.99)
                mock_box = [random.uniform(0.1, 0.9), random.uniform(0.1, 0.9), random.uniform(0.1, 0.3), random.uniform(0.1, 0.3)]

                class MockBoxData:
                    def __init__(self, cls_id, conf, xywhn):
                        self.cls = [cls_id]
                        self.conf = [conf]
                        self.xywhn = [xywhn]
                    
                    def numpy(self):
                        return [MockBoxData(self.cls[0], self.conf[0], self.xywhn[0])]
                        
                # Mock YOLO Results 구조에 맞게 생성
                yield type('MockResults', (object,), {
                    'boxes': type('MockBoxes', (object,), {
                        'cpu': lambda: type('MockCPU', (object,), {
                            'numpy': lambda: [
                                type('MockBox', (object,), {
                                    'cls': np.array([mock_cls_id]),
                                    'conf': np.array([mock_conf]),
                                    'xywhn': np.array([mock_box]),
                                })
                            ]
                        })
                    }),
                    'names': mock_class_map
                })
                time.sleep(1)
        
        results_generator = mock_results_generator()
        model = type('MockModel', (object,), {'names': {0: 'fire', 1: 'smoke', 2: 'person'}})
    else:
        results_generator = model.predict(source=source, stream=True, conf=0.5, show=False)


    for results in results_generator:
        
        is_fire_detected_in_frame = False
        is_smoke_detected_in_frame = False
        detection_details = []
        
        boxes = results.boxes.cpu().numpy()
        
        if len(boxes) == 0:
            pass

        for box in boxes:
            
            cls_name = "unknown"
            conf = 0.0
            x_center, y_center, w, h = 0.0, 0.0, 0.0, 0.0

            if hasattr(box, 'cls') and hasattr(box.cls, 'size') and box.cls.size > 0:
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, "unknown")
                conf = float(box.conf[0])
                x_center, y_center, w, h = box.xywhn[0]
            
            elif hasattr(box, 'conf'):
                cls_id = int(box.cls[0])
                cls_name = results.names.get(cls_id, "unknown")
                conf = float(box.conf[0])
                x_center, y_center, w, h = box.xywhn[0]
            
            else:
                continue 

            normalized_cls_name = cls_name.lower()

            is_fire_flag = normalized_cls_name in FIRE_CLASS_NAMES
            is_smoke_flag = normalized_cls_name in SMOKE_CLASS_NAMES

            if is_fire_flag:
                is_fire_detected_in_frame = True
            
            if is_smoke_flag:
                is_smoke_detected_in_frame = True
            
            detection_details.append({
                "object_type": cls_name,
                "confidence": round(conf, 4),
                "location_x": round(float(x_center), 4),
                "location_y": round(float(y_center), 4),
                "box_w": round(float(w), 4),
                "box_h": round(float(h), 4),
            })

        if len(detection_details) > 0:
            first_detection = detection_details[0]
            payload_compatible = {
                "ai_server_id": AI_SERVER_ID,
                "object_type": first_detection['object_type'], 
                "confidence": first_detection['confidence'],
                "location_x": first_detection['location_x'], 
                "location_y": first_detection['location_y'], 
                "box_w": first_detection['box_w'],  
                "box_h": first_detection['box_h'],
                "is_fire_detected": is_fire_detected_in_frame, 
                "is_smoke_detected": is_smoke_detected_in_frame 
            }
        else:
             payload_compatible = {
                "ai_server_id": AI_SERVER_ID,
                "object_type": "None", 
                "confidence": 0.0,
                "location_x": 0.0, 
                "location_y": 0.0, 
                "box_w": 0.0,  
                "box_h": 0.0,
                "is_fire_detected": False, 
                "is_smoke_detected": False 
            }

        
        current_time = time.time()
        
        if current_time >= next_submission_time:
            
            try:
                response = requests.post(FASTAPI_ENDPOINT, json=payload_compatible, timeout=2)
                
                if response.status_code in [200, 201]: 
                    status_text = "🚨 경보" if is_fire_detected_in_frame or is_smoke_detected_in_frame else "🟢 정상"
                    print(f"\n[10초 전송] ✅ SUCCESS: 프레임 전송 완료. 상태: {status_text} (총 {len(detection_details)}개 객체 감지)")
                else:
                    error_details = response.json()
                    print(f"❌ FAILURE: 프레임 전송 실패! 코드: {response.status_code}")
                    print(f"   🚨 서버 응답 에러: {error_details}") 
            except requests.exceptions.ConnectionError:
                print("🚨 CONNECTION FAILED: FastAPI 서버 연결 안 됨! 서버(main.py)가 켜져 있는지 확인하세요.")
            except requests.exceptions.Timeout:
                print("⏳ TIMEOUT: 서버 응답 지연.")
                
            next_submission_time = current_time + SUBMISSION_INTERVAL
        
        time.sleep(0.05)