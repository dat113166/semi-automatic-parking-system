# main_app.py (AI Worker) — phiên bản có Burst Voting
import cv2
from ultralytics import YOLO
import numpy as np
import requests
import time
import os
from collections import Counter

# ---- Cấu hình ----
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "my-very-strong-secret")
CAMERA_STREAM_URL = os.getenv("CAMERA_STREAM_URL", "http://192.168.1.3:8080/video")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "2"))

# Burst voting
BURST_FRAMES = int(os.getenv("BURST_FRAMES", "6"))       # số frame cho 1 nhiệm vụ
BURST_SLEEP  = float(os.getenv("BURST_SLEEP", "0.03"))   # delay giữa frame burst (giây)

# ---- Tải các mô hình ----
print("Loading models...")
plate_detector = YOLO('models/plate_detector.pt')
char_recognizer = YOLO('models/char_recognizer.pt')
CHAR_CLASS_NAMES = char_recognizer.model.names
print("Models loaded.")

# ---- Tham số định dạng/tiền xử lý chuỗi ----
LINE_SEPARATION_THRESHOLD_FACTOR = 0.7

def normalize_plate(s: str) -> str:
    """Chuẩn hóa chuỗi: giữ A-Z,0-9,'-',' ' và đổi O->0 khi chuỗi thiên về số."""
    import re
    s = re.sub(r"[^A-Za-z0-9\- ]", "", s).upper().strip()
    if sum(ch.isdigit() for ch in s) >= sum(ch.isalpha() for ch in s):
        s = s.replace("O", "0")
    return s

# ---- Hàm xử lý biển số (bạn đã có) ----
def format_plate_text(char_detections):
    if not char_detections:
        return ""
    avg_h = np.mean([y2 - y1 for x1, y1, x2, y2, _ in char_detections])
    if avg_h <= 0:
        return ""

    # tách 2 dòng bằng K-means 2 cụm trên toạ độ y
    cy = np.array([(y1 + y3) / 2 for (_, y1, _, y3, _) in char_detections])
    from sklearn.cluster import KMeans
    if len(char_detections) > 3:
        km = KMeans(n_clusters=2, n_init=5).fit(cy.reshape(-1, 1))
        labels = km.labels_
        groups = [[], []]
        for g, c in zip(labels, char_detections):
            groups[g].append(c)
        # sắp theo vị trí trên–dưới
        groups.sort(key=lambda L: np.mean([(c[1] + c[3]) / 2 for c in L]))
    else:
        groups = [char_detections]

    # sắp trái→phải trong từng dòng
    lines = []
    for g in groups:
        g.sort(key=lambda c: c[0])
        lines.append("".join([c[4] for c in g]))
    return " ".join(lines)

# ---- Helpers cho Burst Voting ----
def pick_best_plate_box(plate_results):
    """Chọn bbox biển có confidence cao nhất."""
    if not plate_results or not plate_results.boxes or len(plate_results.boxes) == 0:
        return None
    return max(plate_results.boxes, key=lambda box: float(box.conf))

def score_candidate(text: str, char_count: int, plate_conf: float) -> float:
    """Điểm gộp đơn giản để tie-break (ưu tiên có nhiều ký tự hợp lệ + conf bbox)."""
    # điểm = (độ dài sau loại space) + 0.2*plate_conf
    core_len = len(text.replace(" ", ""))
    return core_len + 0.2 * float(plate_conf or 0.0)

def majority_vote_text(candidates):
    """
    candidates: list dict { "text": str, "score": float }
    -> trả về text được chọn: ưu tiên đa số; nếu hòa thì lấy text có score cao nhất; nếu vẫn hòa lấy dài nhất.
    """
    non_empty = [c["text"] for c in candidates if c["text"]]
    if not non_empty:
        return ""
    counts = Counter(non_empty)
    most_common = counts.most_common()
    top_text, top_freq = most_common[0]

    # có nhiều text cùng tần suất? chọn theo score cao nhất
    ties = [t for t,f in most_common if f == top_freq]
    if len(ties) == 1:
        return top_text

    # tie-break theo score
    best = None
    best_score = -1e9
    for t in ties:
        # lấy max score trong số các candidate có text == t
        max_score_for_t = max([c["score"] for c in candidates if c["text"] == t], default=-1e9)
        if max_score_for_t > best_score:
            best_score = max_score_for_t
            best = t

    # nếu vẫn None (khó xảy ra), lấy chuỗi dài nhất
    if best is None:
        best = max(ties, key=lambda s: len(s.replace(" ","")))
    return best

# ---- Hàm thực thi nhiệm vụ (có Burst Voting) ----
def process_capture_task(session_id, cap):
    print(f"Processing task for session_id: {session_id}")

    frame_candidates = []  # lưu ứng viên theo từng frame: dict{text, score, meta}

    for i in range(BURST_FRAMES):
        ret, frame = cap.read()
        if not ret:
            print("Warn: Could not read frame from camera (burst).")
            time.sleep(BURST_SLEEP)
            continue

        # 1) Phát hiện biển số
        plate_results = plate_detector(frame, verbose=False)[0]
        best_box = pick_best_plate_box(plate_results)
        if best_box is None:
            time.sleep(BURST_SLEEP)
            continue

        x1, y1, x2, y2 = map(int, best_box.xyxy[0])
        plate_conf = float(best_box.conf)
        plate_crop = frame[y1:y2, x1:x2]
        if plate_crop.size == 0:
            time.sleep(BURST_SLEEP)
            continue

        # 2) Nhận dạng ký tự (dùng ngưỡng như bản cũ: 0.5)
        char_results = char_recognizer(plate_crop, verbose=False)[0]
        char_detections = []
        if char_results and char_results.boxes is not None and char_results.boxes.data is not None:
            for char in char_results.boxes.data.tolist():
                cx1, cy1, cx2, cy2, c_score, c_class_id = char
                if c_score < 0.5:
                    continue
                char_name = CHAR_CLASS_NAMES[int(c_class_id)]
                char_detections.append([cx1, cy1, cx2, cy2, char_name])

        # 3) Ghép chuỗi + chuẩn hóa
        raw_text = format_plate_text(char_detections)
        plate_text = normalize_plate(raw_text)

        # 4) Tính điểm + lưu ứng viên
        sc = score_candidate(plate_text, len(char_detections), plate_conf)
        frame_candidates.append({
            "text": plate_text,
            "score": sc,
            "meta": {
                "bbox": [x1, y1, x2, y2],
                "plate_conf": plate_conf,
                "num_chars": len(char_detections)
            }
        })

        time.sleep(BURST_SLEEP)

    # 5) Bỏ phiếu chọn kết quả cuối
    if not frame_candidates:
        print("No candidates collected in burst.")
        return

    final_text = majority_vote_text(frame_candidates)
    # Lấy meta của ứng viên có cùng text và score cao nhất
    same_text = [c for c in frame_candidates if c["text"] == final_text]
    if same_text:
        best_meta = max(same_text, key=lambda c: c["score"])["meta"]
    else:
        best_meta = max(frame_candidates, key=lambda c: c["score"])["meta"]  # fallback

    if final_text:
        print(f"[BURST] Final plate: {final_text} (from {len(frame_candidates)} frames) -> sending...")
        try:
            response = requests.post(
                f"{BACKEND_URL}/update-plate",
                json={
                    "session_id": session_id,
                    "plate_text": final_text,
                    # gửi thêm một ít meta cơ bản cho backend tiện log (optional)
                    "num_frames": len(frame_candidates),
                    "plate_conf": best_meta.get("plate_conf", None),
                    "plate_bbox": best_meta.get("bbox", None),
                    "num_chars": best_meta.get("num_chars", None)
                },
                headers={"X-Secret": SECRET_KEY},
                timeout=5
            )
            response.raise_for_status()
            print(f"Successfully updated plate for session {session_id}.")
        except requests.exceptions.RequestException as e:
            print(f"Error sending plate data to backend: {e}")
    else:
        print("[BURST] Could not read any characters from the detected plates.")

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
            response = requests.get(f"{BACKEND_URL}/capture-task", headers={"X-Secret": SECRET_KEY}, timeout=5)
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
