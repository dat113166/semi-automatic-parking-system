import cv2, time, os, numpy as np
from ultralytics import YOLO
from ui_display import UIDisplay  # dùng lại UI đã tách

CAM = os.getenv("CAMERA_STREAM_URL", "http://192.168.1.3:8080/video")

plate_detector = YOLO('models/plate_detector.pt')
char_recognizer = YOLO('models/char_recognizer.pt')
CHAR_CLASS_NAMES = char_recognizer.model.names

def normalize_plate(s):
    import re
    s = re.sub(r"[^A-Za-z0-9\- ]","", s).upper().strip()
    if sum(ch.isdigit() for ch in s) >= sum(ch.isalpha() for ch in s):
        s = s.replace("O","0")
    return s

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


cap = cv2.VideoCapture(CAM)
if not cap.isOpened():
    print("Cannot open camera"); raise SystemExit

ui = UIDisplay("ANPR Preview Check", max_width=900, max_height=650, allow_resize=True)

try:
    while True:
        ok, frame = cap.read()
        if not ok: ui.show_stream_lost(int(cap.get(3)), int(cap.get(4))); 
        # phát hiện biển
        pr = plate_detector(frame, verbose=False)[0]
        if pr.boxes is not None and len(pr.boxes) > 0:
            best = max(pr.boxes, key=lambda b: float(b.conf))
            x1,y1,x2,y2 = map(int, best.xyxy[0]); conf = float(best.conf)
            crop = frame[y1:y2, x1:x2]
            crop = rectify_plate(crop)
            crop = enhance_plate(crop)

            # ocr ký tự
            cr = char_recognizer(crop, verbose=False)[0]
            dets = []
            if cr.boxes is not None and cr.boxes.data is not None:
                for cx1,cy1,cx2,cy2,cs,cc in cr.boxes.data.tolist():
                    if cs>=0.5: dets.append([cx1,cy1,cx2,cy2, CHAR_CLASS_NAMES[int(cc)]])
            text = normalize_plate(format_plate_text(dets))
            # overlay
            vis = frame.copy()
            cv2.rectangle(vis,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.putText(vis, f"{text or '...'} ({conf:.2f})", (x1,max(20,y1-8)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
            # panel
            ph=80; panel=np.zeros((ph, vis.shape[1], 3), dtype="uint8")
            cv2.putText(panel, f"text: {text or '...'} | conf: {conf:.2f} | chars: {len(dets)}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
            ui.render(vis, panel=panel)
        else:
            ui.render(frame)

        if cv2.waitKey(1) & 0xFF == ord('q'): break
        time.sleep(0.01)
finally:
    cap.release(); ui.close()
