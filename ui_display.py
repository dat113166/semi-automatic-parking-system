# ui_display.py
import cv2
import numpy as np

class UIDisplay:
    """
    Điều khiển cửa sổ hiển thị OpenCV:
      - Gom panel debug + frame
      - Tự scale về kích thước tối đa (không phóng to)
      - Cho phép kéo/resize cửa sổ (WINDOW_NORMAL|WINDOW_KEEPRATIO)
      - Overlay khi mất stream
    """

    def __init__(self,
                 win_name: str = "Parking System - Press Q to quit",
                 max_width: int = 900,
                 max_height: int = 650,
                 allow_resize: bool = True):
        self.win_name = win_name
        self.max_w = int(max_width)
        self.max_h = int(max_height)

        flags = cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO if allow_resize else cv2.WINDOW_AUTOSIZE
        cv2.namedWindow(self.win_name, flags)
        cv2.resizeWindow(self.win_name, self.max_w, self.max_h)

    def _stack(self, panel: np.ndarray | None, frame: np.ndarray) -> np.ndarray:
        if panel is None:
            return frame
        pw, fw = panel.shape[1], frame.shape[1]
        if pw != fw:
            scale = fw / pw
            ph = int(panel.shape[0] * scale)
            panel = cv2.resize(panel, (fw, ph))
        return np.vstack((panel, frame))

    def _fit_to_max(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        scale = min(self.max_w / w, self.max_h / h, 1.0)  # không phóng to
        if scale < 1.0:
            return cv2.resize(img, (int(w * scale), int(h * scale)))
        return img

    def render(self, frame: np.ndarray, panel: np.ndarray | None = None) -> None:
        combined = self._stack(panel, frame)
        disp = self._fit_to_max(combined)
        cv2.imshow(self.win_name, disp)

    def render_image(self, img: np.ndarray) -> None:
        disp = self._fit_to_max(img)
        cv2.imshow(self.win_name, disp)

    def show_stream_lost(self, width: int, height: int, panel_h: int = 0) -> None:
        H = int(height + panel_h)
        W = int(width)
        black = np.zeros((max(100, H), max(200, W), 3), dtype="uint8")
        cv2.putText(
            black, "STREAM LOST - CHECK CAMERA URL/IP",
            (40, max(40, H // 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2
        )
        self.render_image(black)

    def set_max_size(self, max_width: int, max_height: int) -> None:
        self.max_w = int(max_width)
        self.max_h = int(max_height)
        cv2.resizeWindow(self.win_name, self.max_w, self.max_h)

    def close(self) -> None:
        try:
            cv2.destroyWindow(self.win_name)
        except:
            cv2.destroyAllWindows()
