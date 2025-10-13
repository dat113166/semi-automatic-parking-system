# main_app.py

import cv2
from ultralytics import YOLO
import numpy as np

# --- 1. TẢI CÁC MÔ HÌNH ---
plate_detector = YOLO('models/plate_detector.pt')
char_recognizer = YOLO('models/char_recognizer.pt')
char_list = char_recognizer.model.names


# --- 2. HÀM XỬ LÝ KẾT QUẢ (giữ nguyên hàm format_plate_text) ---
def format_plate_text(char_detections):
    if not char_detections: return ""
    # Xác định các dòng dựa trên trung vị của tọa độ y
    y_coords = [((char[1] + char[3]) / 2) for char in char_detections]
    median_y = np.median(y_coords)
    
    line1, line2 = [], []
    for char in char_detections:
        char_center_y = (char[1] + char[3]) / 2
        # Phân dòng dựa trên việc tâm ký tự ở trên hay dưới ngưỡng trung vị
        # Thêm một khoảng đệm nhỏ (chiều cao trung bình của ký tự / 4) để xử lý biển số hơi nghiêng
        char_height = char[3] - char[1]
        if char_center_y < median_y + (char_height / 4):
            line1.append(char)
        else:
            line2.append(char)

    sorted_line1 = sorted(line1, key=lambda x: x[0])
    sorted_line2 = sorted(line2, key=lambda x: x[0])
    plate_text_line1 = "".join([char[4] for char in sorted_line1])
    plate_text_line2 = "".join([char[4] for char in sorted_line2])
    return f"{plate_text_line1}{plate_text_line2}"

# --- 3. KHỞI ĐỘNG CAMERA VÀ VÒNG LẶP CHÍNH ---
URL = "http://10.168.9.51:8080/video"
cap = cv2.VideoCapture(URL)
if not cap.isOpened():
    print("Lỗi: Không thể mở camera")
    exit()

# Lấy kích thước khung hình
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Cấu hình cho bảng điều khiển
panel_height = 100
panel_color = (0, 0, 0) # Màu đen
debug_plate_size = (200, 60) # Kích thước cố định cho ảnh biển số crop

# --- 4. BẮT ĐẦU TRACKING ---
results_generator = plate_detector.track(source=URL, show=False, stream=True, persist=True)

for frame_results in results_generator:
    frame = frame_results.orig_img
    
    # Tạo bảng điều khiển ở phía trên
    debug_panel = np.zeros((panel_height, frame_width, 3), dtype="uint8")
    
    plate_text = "N/A" # Giá trị mặc định
    
    if frame_results.boxes.id is not None:
        boxes = frame_results.boxes.xyxy.cpu().numpy().astype(int)
        ids = frame_results.boxes.id.cpu().numpy().astype(int)
        confs = frame_results.boxes.conf.cpu().numpy()

        # Chỉ xử lý đối tượng có ID lớn nhất (thường là đối tượng ổn định nhất)
        if len(ids) > 0:
            best_track_idx = np.argmax(confs)
            box, track_id, conf = boxes[best_track_idx], ids[best_track_idx], confs[best_track_idx]

            x1, y1, x2, y2 = box
            
            # Vẽ hộp chữ nhật lên frame chính
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID: {track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            # Cắt và xử lý ảnh biển số
            plate_crop = frame[y1:y2, x1:x2]
            if plate_crop.size > 0:
                # Hiển thị ảnh crop lên bảng điều khiển
                plate_crop_resized = cv2.resize(plate_crop, debug_plate_size)
                debug_panel[20 : 20 + debug_plate_size[1], 20 : 20 + debug_plate_size[0]] = plate_crop_resized
                
                # Nhận dạng ký tự
                chars = char_recognizer(plate_crop)[0]
                char_detections_for_plate = []
                for char in chars.boxes.data.tolist():
                    cx1, cy1, cx2, cy2, c_score, c_class_id = char
                    if c_score < 0.5: continue
                    char_name = char_list[int(c_class_id)]
                    char_detections_for_plate.append([cx1, cy1, cx2, cy2, char_name])

                plate_text = format_plate_text(char_detections_for_plate) or "READING..."

    # Hiển thị thông tin lên bảng điều khiển
    cv2.putText(debug_panel, "TRACKED PLATE:", (debug_plate_size[0] + 40, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(debug_panel, plate_text, (debug_plate_size[0] + 40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # Ghép bảng điều khiển và frame chính
    combined_frame = np.vstack((debug_panel, frame))

    # Hiển thị video
    cv2.imshow('Parking System - Press Q to quit', combined_frame)

    if cv2.waitKey(1) == ord('q'):
        break

# Dọn dẹp
cap.release()
cv2.destroyAllWindows()