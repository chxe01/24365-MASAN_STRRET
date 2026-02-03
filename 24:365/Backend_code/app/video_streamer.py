import cv2
import threading
import time
import numpy as np

COLOR_MAP = {
    'fire': (0, 0, 255),
    'smoke': (0, 165, 255),
    'person': (255, 0, 0),
    'car': (0, 255, 0),
    'unknown': (255, 255, 255),
}
FONT = cv2.FONT_HERSHEY_SIMPLEX
LINE_THICKNESS = 2
TEXT_SCALE = 0.7

class VideoStreamer:
    def __init__(self, src=0):
        self.stream = None
        try:
            self.stream = cv2.VideoCapture(src)
        except Exception as e:
            print(f"🚨🚨 cv2.VideoCapture({src}) 초기화 중 오류 발생: {e}")

        self.src = src
        self.lock = threading.Lock()
        self.frame = None
        self.stopped = False

        self.current_detections = {}

        if not self.stream or not self.stream.isOpened():
            print(f"🚨🚨 Camera {src} failed to open.")
            self.stream = None
            return

        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()

        time.sleep(1.0)
        print(f"✅ VideoStreamer initialized for source {src}.")

    def set_detections(self, detections: dict):
        with self.lock:
            self.current_detections = detections.copy()

    def update(self):
        while not self.stopped:
            if self.stream and self.stream.isOpened():
                (grabbed, frame) = self.stream.read()
                if not grabbed:
                    self.stopped = True
                    break

                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.1)

        if self.stream:
            self.stream.release()
            print(f"✅ Camera {self.src} stream released.")

    def draw_detections(self, frame, detections: dict):
        if frame is None or not detections:
            return frame

        (H, W) = frame.shape[:2]

        for server_id, detection_list in detections.items():
            for det in detection_list:
                try:
                    center_x_norm = det.get('location_x')
                    center_y_norm = det.get('location_y')
                    w_norm = det.get('width_norm')
                    h_norm = det.get('height_norm')

                    object_type = det.get('object_type', 'unknown')
                    confidence = det.get('confidence', 0.0)

                    if center_x_norm is None or center_y_norm is None or w_norm is None or h_norm is None:
                        continue

                    center_x = int(center_x_norm * W)
                    center_y = int(center_y_norm * H)

                    box_w = int(w_norm * W)
                    box_h = int(h_norm * H)

                    x1 = max(0, int(center_x - box_w / 2))
                    y1 = max(0, int(center_y - box_h / 2))
                    x2 = min(W, int(center_x + box_w / 2))
                    y2 = min(H, int(center_y + box_h / 2))

                    color = COLOR_MAP.get(object_type, COLOR_MAP['unknown'])
                    label = f"{object_type}: {confidence:.2f}"

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, LINE_THICKNESS)

                    (text_w, text_h), baseline = cv2.getTextSize(label, FONT, TEXT_SCALE, LINE_THICKNESS)

                    text_y = y1 - text_h - 10
                    if text_y < 0:
                        text_y = y2 + text_h + 10

                    cv2.rectangle(frame, (x1, text_y - text_h), (x1 + text_w + 10, text_y + baseline), color, -1)
                    cv2.putText(frame, label, (x1 + 5, text_y), FONT, TEXT_SCALE, (255, 255, 255), LINE_THICKNESS, cv2.LINE_AA)

                except Exception as e:
                    print(f"⚠️ 바운딩 박스 그리기 중 런타임 오류: {e}")
                    continue

        return frame

    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return self.get_black_frame()

            processed_frame = self.frame.copy()

            if self.current_detections:
                 processed_frame = self.draw_detections(processed_frame, self.current_detections)

            ret, jpeg = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

            if ret:
                return jpeg.tobytes()
            else:
                print("❌ JPEG 인코딩 실패!")
                return self.get_black_frame()

    def get_black_frame(self):
        black_image = np.zeros((360, 480, 3), dtype=np.uint8)
        text = "NO VIDEO STREAM / CAM FAILED"
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.8
        font_thickness = 2
        text_size = cv2.getTextSize(text, font, font_scale, font_thickness)[0]
        text_x = (black_image.shape[1] - text_size[0]) // 2
        text_y = (black_image.shape[0] + text_size[1]) // 2
        cv2.putText(black_image, text, (text_x, text_y), font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)

        ret, jpeg = cv2.imencode('.jpg', black_image)
        if ret:
            return jpeg.tobytes()
        return b''

    def stop(self):
        self.stopped = True
        if self.thread.is_alive():
            self.thread.join()