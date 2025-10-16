# main_app.py — ANPR Hybrid + Stable Preview (Lock + EMA) + Fallback + SafeCrop
# (ĐÃ CHÈN: last_preview_img, safe_crop, best-frame fallback, lock state, stream-lost overlay + tách UI)

import cv2
import numpy as np
from collections import deque, Counter, defaultdict
from ultralytics import YOLO
from ui_display import UIDisplay  # <-- UI tách riêng

# =========================
# 1) MODELS
# =========================
vehicle_detector = YOLO("yolov8n.pt")         # COCO: 2=car, 3=motorcycle
plate_detector   = YOLO("models/plate_detector.pt")
char_recognizer  = YOLO("models/char_recognizer.pt")
CHAR_LIST        = char_recognizer.model.names  # id -> char

# =========================
# 2) UTILS
# =========================
def iou_xyxy(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2-x1) * max(0, y2-y1)
    area_a = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
    area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
    return inter / (area_a + area_b - inter + 1e-9)

def nms_boxes_xyxy(chars, iou_thresh=0.25):
    if not chars: return []
    chars = sorted(chars, key=lambda c: c["conf"], reverse=True)
    kept, sup = [], [False]*len(chars)
    for i in range(len(chars)):
        if sup[i]: continue
        kept.append(chars[i])
        for j in range(i+1, len(chars)):
            if sup[j]: continue
            if iou_xyxy(
                (chars[i]["x1"], chars[i]["y1"], chars[i]["x2"], chars[i]["y2"]),
                (chars[j]["x1"], chars[j]["y1"], chars[j]["x2"], chars[j]["y2"])
            ) > iou_thresh:
                sup[j] = True
    return kept

def order_quad_pts(pts):
    s = pts.sum(axis=1); d = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]; br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]; bl = pts[np.argmax(d)]
    return np.array([tl,tr,br,bl], dtype="float32")

def rectify_plate(img):
    if img is None or img.size == 0: return img
    H, W = img.shape[:2]
    if H < 10 or W < 10: return img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(blur, 50, 150)
    cnts,_ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts: return img
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.1*H*W: return img
    rect = cv2.minAreaRect(c)
    box  = order_quad_pts(cv2.boxPoints(rect).astype("float32"))
    (tl,tr,br,bl) = box
    maxW = int(max(np.linalg.norm(br-bl), np.linalg.norm(tr-tl)))
    maxH = int(max(np.linalg.norm(tr-br), np.linalg.norm(tl-bl)))
    maxW = max(32, min(maxW, 1024)); maxH = max(16, min(maxH, 512))
    M = cv2.getPerspectiveTransform(box, np.array([[0,0],[maxW-1,0],[maxW-1,maxH-1],[0,maxH-1]], dtype="float32"))
    return cv2.warpPerspective(img, M, (maxW, maxH))

def enhance_plate(img):
    if img is None or img.size == 0: return img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    cl = clahe.apply(gray)
    cl = cv2.morphologyEx(cl, cv2.MORPH_OPEN, np.ones((2,2), np.uint8))
    h,w = cl.shape[:2]
    target_h = 64 if h < 64 else h
    scale = target_h / float(h)
    cl = cv2.resize(cl, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(cl, cv2.COLOR_GRAY2BGR)

def should_replace_O_with_0(s):
    return sum(c.isdigit() for c in s) >= sum(c.isalpha() for c in s)

def postprocess_plate(s):
    import re
    s = re.sub(r'[^A-Za-z0-9\- ]','', s).upper().strip()
    if should_replace_O_with_0(s): s = s.replace('O','0')
    return s

def extract_chars_from_yolo_result(result, conf_thres=0.15):
    out = []
    if result is None or result.boxes is None or result.boxes.data is None:
        return out
    for r in result.boxes.data.tolist():
        x1,y1,x2,y2,conf,cls_id = r[:6]
        if conf < conf_thres: continue
        label = str(CHAR_LIST[int(cls_id)])
        out.append({
            "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
            "cx": float((x1+x2)/2), "cy": float((y1+y2)/2),
            "w": float(x2-x1), "h": float(y2-y1),
            "label": label, "conf": float(conf)
        })
    return out

def format_plate_text_v2(char_dets):
    if not char_dets: return ""
    chars = nms_boxes_xyxy(char_dets, iou_thresh=0.25)
    if not chars: return ""
    avg_h = float(np.mean([c["h"] for c in chars])) if chars else 0.0
    if avg_h <= 0: return ""
    chars.sort(key=lambda c: c["cy"])
    lines, cur = [], [chars[0]]
    for ch in chars[1:]:
        if abs(ch["cy"] - cur[-1]["cy"]) < 0.60 * avg_h: cur.append(ch)
        else: lines.append(cur); cur = [ch]
    lines.append(cur)
    txts = []
    for line in lines:
        line = sorted(line, key=lambda c: c["cx"])
        txts.append("".join([c["label"] for c in line if c["conf"] > 0.35]))
    return postprocess_plate(" ".join([t for t in txts if t]))

def score_plate(plate_text, char_dets):
    if not char_dets: return 0.0
    avg_conf = np.mean([c["conf"] for c in char_dets]) if char_dets else 0.0
    valid = sum(ch.isalnum() for ch in plate_text)
    return valid + 0.5 * avg_conf

# =========================
# 3) SMOOTHING TEXT + PREVIEW LOCK
# =========================
plate_history = defaultdict(lambda: deque(maxlen=8))

def add_plate_reading(key, text):
    if text: plate_history[key].append(text)

def best_plate_from_history(key):
    if key not in plate_history or not plate_history[key]: return None
    cnt = Counter(plate_history[key])
    return cnt.most_common(1)[0][0]

def bbox_center_key(x1,y1,x2,y2, grid=60):
    return (int(((x1+x2)/2)//grid), int(((x1+x2)/2)//grid))  # giữ key ổn định theo tâm (tuỳ ý)

# EMA cho bbox -> crop preview ổn định
bbox_ema = {}
EMA_ALPHA = 0.6

def ema_bbox(key, x1,y1,x2,y2):
    if key not in bbox_ema:
        bbox_ema[key] = (float(x1),float(y1),float(x2),float(y2))
    else:
        px1,py1,px2,py2 = bbox_ema[key]
        bx1 = EMA_ALPHA*x1 + (1-EMA_ALPHA)*px1
        by1 = EMA_ALPHA*y1 + (1-EMA_ALPHA)*py1
        bx2 = EMA_ALPHA*x2 + (1-EMA_ALPHA)*px2
        by2 = EMA_ALPHA*y2 + (1-EMA_ALPHA)*py2
        bbox_ema[key] = (bx1,by1,bx2,by2)
    return tuple(map(int, bbox_ema[key]))

# Lock preview (hysteresis)
locked_key = None
locked_best_score = -1.0
locked_stable_count = 0
locked_missing_count = 0
LOCK_MIN_STABLE = 3
LOCK_MISS_TOL   = 12

def update_lock(curr_key, curr_score, has_detection):
    global locked_key, locked_best_score, locked_stable_count, locked_missing_count
    if locked_key is None:
        if has_detection:
            locked_key, locked_best_score = curr_key, curr_score
            locked_stable_count, locked_missing_count = 1, 0
        return
    if has_detection and curr_key == locked_key:
        locked_missing_count = 0
        if curr_score > locked_best_score:
            locked_best_score = curr_score
        return
    if has_detection and curr_key != locked_key:
        if curr_score >= locked_best_score + 1.0:
            locked_stable_count += 1
            if locked_stable_count >= LOCK_MIN_STABLE:
                locked_key, locked_best_score = curr_key, curr_score
                locked_stable_count, locked_missing_count = 0, 0
        else:
            locked_stable_count = 0
            locked_missing_count = 0
        return
    if not has_detection:
        locked_missing_count += 1
        if locked_missing_count >= LOCK_MISS_TOL:
            locked_key = None
            locked_best_score = -1.0
            locked_stable_count = 0
            locked_missing_count = 0

# ========== PATCH #1: last good preview buffer ==========
last_preview_img = None

# ========== PATCH #2: safe crop ==========
def safe_crop(img, x1,y1,x2,y2):
    if img is None or img.size == 0: return None
    H, W = img.shape[:2]
    x1 = max(0, min(int(x1), W-1))
    x2 = max(0, min(int(x2), W))
    y1 = max(0, min(int(y1), H-1))
    y2 = max(0, min(int(y2), H))
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2]

# =========================
# 4) CAMERA & UI
# =========================
URL = "http://10.146.44.250:8080/video"  # đổi URL nếu dùng IP webcam phone
# cap = cv2.VideoCapture(0)  # dùng webcam máy tính thì bật dòng này và tắt dòng URL
cap = cv2.VideoCapture(URL)
if not cap.isOpened():
    print("[ERR] Không mở được stream. Kiểm tra URL/IP.")
    raise SystemExit

fw  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 640
fh  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
panel_h = 110
debug_plate_size = (220, 70)

# UI: set kích thước cửa sổ tối đa (muốn nhỏ hơn nữa thì giảm số dưới)
ui = UIDisplay(
    win_name="Parking System - Press Q to quit",
    max_width=900,
    max_height=650,
    allow_resize=True
)

# =========================
# 5) MAIN LOOP
# =========================
while True:
    ok, frame = cap.read()
    if not ok or frame is None or frame.size == 0:
        ui.show_stream_lost(fw, fh, panel_h=panel_h)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    # Ứng viên tốt nhất của frame (PATCH #3)
    best_frame_candidate = {"key": None, "score": -1.0, "crop": None}
    debug_panel = np.zeros((panel_h, fw, 3), dtype="uint8")

    # PATCH #1b: show last preview if no new yet
    if last_preview_img is not None:
        try:
            debug_panel[20:20+debug_plate_size[1], 20:20+debug_plate_size[0]] = last_preview_img
        except:
            pass

    final_plate_text = "N/A"

    # Detect
    veh_res = vehicle_detector(frame, classes=[2,3], conf=0.5)[0]
    plt_res = plate_detector(frame, conf=0.55)[0]

    vehicles, plates = [], []
    if veh_res.boxes is not None and veh_res.boxes.data is not None:
        for v in veh_res.boxes.data.tolist():
            vx1,vy1,vx2,vy2,vconf,vcls = v[:6]
            vehicles.append((int(vx1),int(vy1),int(vx2),int(vy2), float(vconf), int(vcls)))
    if plt_res.boxes is not None and plt_res.boxes.data is not None:
        for p in plt_res.boxes.data.tolist():
            px1,py1,px2,py2,pconf,pcls = p[:6]
            plates.append((int(px1),int(py1),int(px2),int(py2), float(pconf), int(pcls)))

    processed = set()

    # ƯU TIÊN 1: gán plate cho vehicle (center-in)
    for vx1,vy1,vx2,vy2,vconf,vcls in vehicles:
        for j,(px1,py1,px2,py2,pconf,pcls) in enumerate(plates):
            if j in processed: continue
            pcx, pcy = (px1+px2)/2.0, (py1+py2)/2.0
            if vx1 < pcx < vx2 and vy1 < pcy < vy2:
                processed.add(j)

                vname = vehicle_detector.model.names.get(vcls,"VEH")
                cv2.rectangle(frame,(vx1,vy1),(vx2,vy2),(255,0,0),2)
                cv2.putText(frame,f"{vname.upper()} {vconf:.2f}",(vx1,max(20,vy1-8)),
                            cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,0,0),2)
                cv2.rectangle(frame,(px1,py1),(px2,py2),(0,255,0),2)

                key = bbox_center_key(px1,py1,px2,py2, grid=60)
                sx1,sy1,sx2,sy2 = ema_bbox(key, px1,py1,px2,py2)
                preview_crop = safe_crop(frame, sx1,sy1,sx2,sy2)

                ocr_crop = safe_crop(frame, px1,py1,px2,py2)
                if ocr_crop is not None:
                    ocr_crop = rectify_plate(ocr_crop)
                    ocr_crop = enhance_plate(ocr_crop)

                    chars_res = char_recognizer(ocr_crop, conf=0.15)[0]
                    char_dets = extract_chars_from_yolo_result(chars_res, conf_thres=0.15)
                    plate_txt = format_plate_text_v2(char_dets)
                    add_plate_reading(key, plate_txt)
                    smoothed = best_plate_from_history(key)
                    plate_score = score_plate(plate_txt, char_dets)

                    has_det = preview_crop is not None and preview_crop.size > 0
                    update_lock(key, plate_score, has_det)

                    if has_det and plate_score > best_frame_candidate["score"]:
                        best_frame_candidate = {"key": key, "score": plate_score, "crop": preview_crop.copy()}

                    if locked_key == key and has_det:
                        try:
                            plate_preview = cv2.resize(preview_crop, debug_plate_size)
                            debug_panel[20:20+debug_plate_size[1], 20:20+debug_plate_size[0]] = plate_preview
                            last_preview_img = plate_preview.copy()
                        except:
                            pass

                    final_plate_text = smoothed or plate_txt or "READING..."
                break

    # ƯU TIÊN 2: biển “mồ côi”
    for j,(px1,py1,px2,py2,pconf,pcls) in enumerate(plates):
        if j in processed: continue
        cv2.rectangle(frame,(px1,py1),(px2,py2),(0,255,0),2)

        key = bbox_center_key(px1,py1,px2,py2, grid=60)
        sx1,sy1,sx2,sy2 = ema_bbox(key, px1,py1,px2,py2)
        preview_crop = safe_crop(frame, sx1,sy1,sx2,sy2)

        ocr_crop = safe_crop(frame, px1,py1,px2,py2)
        if ocr_crop is not None:
            ocr_crop = rectify_plate(ocr_crop)
            ocr_crop = enhance_plate(ocr_crop)

            chars_res = char_recognizer(ocr_crop, conf=0.15)[0]
            char_dets = extract_chars_from_yolo_result(chars_res, conf_thres=0.15)
            plate_txt = format_plate_text_v2(char_dets)
            add_plate_reading(key, plate_txt)
            smoothed = best_plate_from_history(key)
            plate_score = score_plate(plate_txt, char_dets)

            has_det = preview_crop is not None and preview_crop.size > 0
            update_lock(key, plate_score, has_det)

            if has_det and plate_score > best_frame_candidate["score"]:
                best_frame_candidate = {"key": key, "score": plate_score, "crop": preview_crop.copy()}

            if locked_key == key and has_det:
                try:
                    plate_preview = cv2.resize(preview_crop, debug_plate_size)
                    debug_panel[20:20+debug_plate_size[1], 20:20+debug_plate_size[0]] = plate_preview
                    last_preview_img = plate_preview.copy()
                except:
                    pass

            final_plate_text = smoothed or plate_txt or "READING..."

    # PATCH #3b: nếu chưa lock, show best-frame candidate để tránh đen
    if locked_key is None and best_frame_candidate["crop"] is not None:
        try:
            plate_preview = cv2.resize(best_frame_candidate["crop"], debug_plate_size)
            debug_panel[20:20+debug_plate_size[1], 20:20+debug_plate_size[0]] = plate_preview
            last_preview_img = plate_preview.copy()
        except:
            pass

    # Panel text + trạng thái lock
    lock_state = "LOCKED" if locked_key is not None else "UNLOCKED"
    cv2.putText(debug_panel, f"PREVIEW: {lock_state}", (debug_plate_size[0]+40, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180,180,180), 1)
    cv2.putText(debug_panel, "DETECTED PLATE:", (debug_plate_size[0]+40, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
    cv2.putText(debug_panel, str(final_plate_text), (debug_plate_size[0]+40, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,255,0), 2)

    # === HIỂN THỊ: chỉ 1 dòng, UI tự co nhỏ về max size ===
    ui.render(frame, panel=debug_panel)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
ui.close()
