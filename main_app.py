# main_app.py

import cv2
from ultralytics import YOLO
import numpy as np

# --- 1. TẢI CÁC MÔ HÌNH ---
plate_detector = YOLO('models/plate_detector.pt')
char_recognizer = YOLO('models/char_recognizer.pt')
CHAR_CLASS_NAMES = char_recognizer.model.names


# --- 2. HÀM XỬ LÝ KẾT QUẢ (giữ nguyên hàm format_plate_text) ---
LINE_SEPARATION_THRESHOLD_FACTOR = 0.7 # Ngưỡng để xác định ký tự có cùng hàng hay không

def format_plate_text(char_detections):
    """
    Sắp xếp các ký tự theo quy tắc chuẩn: TỪ TRÊN XUỐNG DƯỚI, TỪ TRÁI SANG PHẢI.
    """
    if not char_detections:
        return ""

    # Xác định chiều cao trung bình của một ký tự
    # để dùng làm ngưỡng phân biệt các hàng
    avg_char_height = np.mean([char[3] - char[1] for char in char_detections])

    # Sắp xếp tất cả các ký tự dựa trên tọa độ y trước tiên
    # Điều này sẽ gom các ký tự cùng hàng lại với nhau
    sorted_by_y = sorted(char_detections, key=lambda x: (x[1] + x[3]) / 2)

    lines = []
    current_line = [sorted_by_y[0]]

    # Lặp qua các ký tự đã sắp xếp theo chiều dọc
    for i in range(1, len(sorted_by_y)):
        prev_char = current_line[-1]
        current_char = sorted_by_y[i]
        
        # Lấy tâm y của ký tự trước và ký tự hiện tại
        prev_center_y = (prev_char[1] + prev_char[3]) / 2
        current_center_y = (current_char[1] + current_char[3]) / 2
        
        # Nếu khoảng cách theo chiều dọc nhỏ (cùng một hàng)
        if abs(current_center_y - prev_center_y) < avg_char_height * LINE_SEPARATION_THRESHOLD_FACTOR:
            current_line.append(current_char)
        else: # Nếu khoảng cách lớn (sang hàng mới)
            lines.append(current_line)
            current_line = [current_char]
    
    # Thêm dòng cuối cùng vào
    lines.append(current_line)

    plate_text = ""
    # Sắp xếp từng dòng theo tọa độ x và ghép lại
    for line in lines:
        sorted_line = sorted(line, key=lambda x: x[0])
        plate_text += "".join([char[4] for char in sorted_line])

    return plate_text

# --- 3. KHỞI ĐỘNG CAMERA VÀ VÒNG LẶP CHÍNH ---
CAMERA_STREAM_URL = "http://192.168.110.127:8080/video"
cap = cv2.VideoCapture(CAMERA_STREAM_URL)
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
results_generator = plate_detector.track(source=CAMERA_STREAM_URL, show=False, stream=True, persist=True)

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
                    char_name = CHAR_CLASS_NAMES[int(c_class_id)]
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