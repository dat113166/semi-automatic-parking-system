# app.py — FastAPI nhận sự kiện từ Colab, lưu SQLite
import os, sqlite3, json
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

SECRET = os.getenv("INGEST_SECRET", "change-me")   # đặt biến môi trường khi chạy
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "events.db")
os.makedirs(DB_DIR, exist_ok=True)  # TỰ TẠO data/ nếu chưa có

app = FastAPI(title="Ingest Server", version="1.0.0")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS events(
          id TEXT PRIMARY KEY,
          ts TEXT,                    -- ISO UTC
          lane_id TEXT,
          vehicle_type TEXT,          -- bicycle | motorbike | car
          plate_text TEXT,            -- có thể NULL
          plate_conf REAL,            -- có thể NULL
          status TEXT,                -- Registered | Not Registered | Not Required
          frame_index INTEGER,        -- tùy chọn
          meta TEXT                   -- JSON string
        );""")
init_db()

class EventIn(BaseModel):
    event_id: str
    timestamp: str
    lane_id: str
    vehicle_type: str
    plate_text: Optional[str] = None
    plate_conf: Optional[float] = None
    status: str
    frame_index: Optional[int] = None
    meta: Optional[Dict] = None

@app.get("/health")
def health():
    return {"ok": True, "server_time": datetime.utcnow().isoformat()+"Z"}
# ===============================================================
# CÁC ENDPOINT MỚI CHO IoT VÀ AI WORKER (Bản Mock)
# ===============================================================

# Biến tạm thời để mô phỏng trạng thái của barrier
BARRIER_STATE = "close"

@app.post("/trigger_capture")
def trigger_capture():
    """
    API này được ESP32 gọi khi cảm biến phát hiện xe.
    Tạm thời chỉ cần nhận lệnh và báo thành công.
    """
    print("Backend received trigger from ESP32!")
    return {"ok": True, "message": "Capture command received"}

@app.post("/set_barrier_state")
def set_barrier_state(state: str):
    """
    API này sẽ được Local AI Worker gọi sau khi xử lý ảnh thành công.
    Nó sẽ cập nhật trạng thái của barrier.
    """
    global BARRIER_STATE
    BARRIER_STATE = state
    print(f"Barrier state set to: {state}")
    return {"ok": True}

@app.get("/barrier_command")
def get_barrier_command():
    """
    API này được ESP32 gọi liên tục để hỏi xem có nên mở barrier không.
    """
    global BARRIER_STATE
    cmd = BARRIER_STATE
    # Reset lại ngay sau khi ESP32 đã nhận lệnh, để nó không mở liên tục
    if cmd == "open":
        BARRIER_STATE = "close"
    return {"command": cmd}
@app.post("/ingest")
def ingest(evt: EventIn, x_ingest_token: str = Header(None)):
    if x_ingest_token != SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""INSERT OR IGNORE INTO events
                       (id, ts, lane_id, vehicle_type, plate_text, plate_conf, status, frame_index, meta)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (evt.event_id,
                     evt.timestamp,
                     evt.lane_id,
                     evt.vehicle_type,
                     evt.plate_text,
                     evt.plate_conf,
                     evt.status,
                     evt.frame_index,
                     json.dumps(evt.meta or {}, ensure_ascii=False)))
    return {"ok": True}

@app.get("/events")
def list_events(limit: int = 50):
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"events": [dict(r) for r in rows]}

# ===============================================================
# CÁC ENDPOINT MỚI CHO IoT VÀ AI WORKER (Bản Mock)
# ===============================================================

# Biến tạm thời để mô phỏng trạng thái của barrier
BARRIER_STATE = "close"

@app.post("/trigger_capture")
def trigger_capture():
    """
    API này được ESP32 gọi khi cảm biến phát hiện xe.
    Tạm thời chỉ cần nhận lệnh và báo thành công.
    """
    print("Backend received trigger from ESP32!")
    return {"ok": True, "message": "Capture command received"}

@app.post("/set_barrier_state")
def set_barrier_state(state: str):
    """
    API này sẽ được Local AI Worker gọi sau khi xử lý ảnh thành công.
    Nó sẽ cập nhật trạng thái của barrier.
    """
    global BARRIER_STATE
    BARRIER_STATE = state
    print(f"Barrier state set to: {state}")
    return {"ok": True}

@app.get("/barrier_command")
def get_barrier_command():
    """
    API này được ESP32 gọi liên tục để hỏi xem có nên mở barrier không.
    """
    global BARRIER_STATE
    cmd = BARRIER_STATE
    # Reset lại ngay sau khi ESP32 đã nhận lệnh, để nó không mở liên tục
    if cmd == "open":
        BARRIER_STATE = "close"
    return {"command": cmd}
