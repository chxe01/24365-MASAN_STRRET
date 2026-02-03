import sys
import os
import traceback 
import asyncio 


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(__file__))


VideoStreamer = None
try:
    from video_streamer import VideoStreamer
    
except Exception as e:
    print(f"❌❌ 치명적인 오류! VideoStreamer 클래스 로드 최종 실패: {e}", file=sys.stderr)
    print("❌❌ (자세한 오류 메시지):")
    traceback.print_exc(file=sys.stderr)
    VideoStreamer = None 
    

vs = None

if VideoStreamer:

    CAMERA_INDEX_TO_TRY = 0 

    print(f"🔄 VideoStreamer가 카메라 인덱스 {CAMERA_INDEX_TO_TRY}로 연결을 시도합니다...")
    
    try:
        vs_instance = VideoStreamer(src=CAMERA_INDEX_TO_TRY) 
        
        if vs_instance: 
            is_opened = vs_instance.stream and vs_instance.stream.isOpened() if hasattr(vs_instance, 'stream') and vs_instance.stream else False

            if is_opened:
                print(f"✅ VideoStreamer 인스턴스 생성 성공! 카메라({CAMERA_INDEX_TO_TRY}) 연결 확인!")
                vs = vs_instance
            else:
                 print(f"❌ VideoStreamer 인스턴스 생성 성공했으나, 카메라({CAMERA_INDEX_TO_TRY}) 열기 실패.")
                 print("   💡 힌트: 다른 인덱스 (1, 2 등)를 시도해 보거나 카메라 연결 상태를 확인하세요.")
                 vs = None 
        else:
            print("❌ VideoStreamer 인스턴스 생성 실패 (알 수 없는 이유).")
            vs = None 
            
    except Exception as e:
        print(f"❌❌ VideoStreamer 인스턴스 초기화 중 오류 발생: {e}", file=sys.stderr)
        print("❌❌ (자세한 오류 메시지):")
        traceback.print_exc(file=sys.stderr)
        vs = None 
else:
    print("❌ VideoStreamer 클래스 로드 실패로 인해, vs 인스턴스는 None으로 설정됩니다.")



async def broadcast_event(message: str, connections: set):

    disconnected_websockets = set()
    
    for websocket in connections:
        try:
            await websocket.send_text(message)
        except Exception:
            disconnected_websockets.add(websocket)

    for websocket in disconnected_websockets:
        if websocket in connections:
            connections.remove(websocket)
            