# main_app.py (AI Worker)
import cv2
from ultralytics import YOLO
import numpy as np
import requests
import time
import os

# ---- Cấu hình ----
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "my-very-strong-secret")
CAMERA_STREAM_URL = os.getenv("CAMERA_STREAM_URL", "http://192.168.110.127:8080/video")
POLL_INTERVAL_SECONDS = 2 # Thời gian chờ giữa các lần hỏi việc

# ---- Tải các mô hình ----
print("Loading models...")
plate_detector = YOLO('models/plate_detector.pt')
char_recognizer = YOLO('models/char_recognizer.pt')
CHAR_CLASS_NAMES = char_recognizer.model.names
print("Models loaded.")

# ---- Hàm xử lý biển số (giữ nguyên) ----
LINE_SEPARATION_THRESHOLD_FACTOR = 0.7
def format_plate_text(char_detections):
    if not char_detections: return ""
    avg_char_height = np.mean([char[3] - char[1] for char in char_detections])
    sorted_by_y = sorted(char_detections, key=lambda x: (x[1] + x[3]) / 2)
    lines, current_line = [], [sorted_by_y[0]]
    for i in range(1, len(sorted_by_y)):
        prev_char, current_char = current_line[-1], sorted_by_y[i]
        prev_center_y = (prev_char[1] + prev_char[3]) / 2
        current_center_y = (current_char[1] + current_char[3]) / 2
        if abs(current_center_y - prev_center_y) < avg_char_height * LINE_SEPARATION_THRESHOLD_FACTOR:
            current_line.append(current_char)
        else:
            lines.append(current_line)
            current_line = [current_char]
    lines.append(current_line)
    plate_text = ""
    for line in lines:
        sorted_line = sorted(line, key=lambda x: x[0])
        plate_text += "".join([char[4] for char in sorted_line])
    return plate_text

# ---- Hàm thực thi nhiệm vụ ----
def process_capture_task(session_id, cap):
    print(f"Processing task for session_id: {session_id}")
    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame from camera.")
        return

    # 1. Phát hiện biển số
    plate_results = plate_detector(frame, verbose=False)[0]
    if not plate_results.boxes:
        print("No plates detected.")
        # Có thể gọi API để báo lỗi ở đây nếu cần
        return

    # 2. Lấy biển số có độ tin cậy cao nhất
    best_plate = max(plate_results.boxes, key=lambda box: box.conf)
    x1, y1, x2, y2 = map(int, best_plate.xyxy[0])
    plate_crop = frame[y1:y2, x1:x2]

    # 3. Nhận dạng ký tự
    char_results = char_recognizer(plate_crop, verbose=False)[0]
    char_detections = []
    for char in char_results.boxes.data.tolist():
        cx1, cy1, cx2, cy2, c_score, c_class_id = char
        if c_score < 0.5: continue
        char_name = CHAR_CLASS_NAMES[int(c_class_id)]
        char_detections.append([cx1, cy1, cx2, cy2, char_name])

    # 4. Định dạng và gửi kết quả
    plate_text = format_plate_text(char_detections)
    if plate_text:
        print(f"Detected plate: {plate_text}. Sending to backend...")
        try:
            response = requests.post(
                f"{BACKEND_URL}/update-plate",
                json={"session_id": session_id, "plate_text": plate_text},
                headers={"X-Secret": SECRET_KEY}
            )
            response.raise_for_status()
            print(f"Successfully updated plate for session {session_id}.")
        except requests.exceptions.RequestException as e:
            print(f"Error sending plate data to backend: {e}")
    else:
        print("Could not read any characters from the detected plate.")


# ---- Vòng lặp chính của Worker ----
def main_loop():
    print("AI Worker started. Connecting to camera...")
    cap = cv2.VideoCapture(CAMERA_STREAM_URL)
    if not cap.isOpened():
        print("FATAL: Cannot open camera stream. Exiting.")
        return

    print(f"Polling backend at {BACKEND_URL} every {POLL_INTERVAL_SECONDS} seconds...")
    while True:
        try:
            # Lấy nhiệm vụ từ backend
            response = requests.get(f"{BACKEND_URL}/capture-task", headers={"X-Secret": SECRET_KEY})
            response.raise_for_status()
            task_data = response.json()

            if task_data.get("task") == "capture_plate":
                session_id = task_data.get("session_id")
                if session_id:
                    process_capture_task(session_id, cap)
                else:
                    print("Warning: Received capture task without a session_id.")

            # Đợi trước khi hỏi việc lần nữa
            time.sleep(POLL_INTERVAL_SECONDS)

        except requests.exceptions.RequestException as e:
            print(f"Could not connect to backend: {e}. Retrying in {POLL_INTERVAL_SECONDS}s...")
            time.sleep(POLL_INTERVAL_SECONDS)
        except Exception as e:
            print(f"An unexpected error occurred: {e}. Retrying in {POLL_INTERVAL_SECONDS}s...")
            time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main_loop()