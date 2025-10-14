# backend_server/app.py (rút gọn phần thay đổi)
import os, sqlite3, uuid
from fastapi import FastAPI, HTTPException, Body, Header, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import asyncio

SECRET = os.getenv("SECRET_KEY", "my-very-strong-secret")
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "parking.db")
os.makedirs(DB_DIR, exist_ok=True)

app = FastAPI(title="Parking System Backend", version="1.1.1")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
          session_id TEXT PRIMARY KEY,
          plate_text TEXT NOT NULL,
          time_in TEXT NOT NULL,
          time_out TEXT,
          status TEXT NOT NULL, -- CHECKED_IN, CHECKED_OUT
          fee REAL
        );""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_plate_status ON sessions(plate_text, status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_time_in ON sessions(time_in)")
init_db()

# ---- Simple auth (tùy chọn) ----
def require_secret(x_secret: Optional[str] = Header(None, alias="X-Secret")):
    if x_secret != SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ---- App-scoped state + lock (an toàn trong 1 worker) ----
app.state.capture_requested = False
app.state.barrier_command = "close"
app.state.lock = asyncio.Lock()

# ---- Models ----
class PlatePayload(BaseModel):
    plate_text: str

# ---- IoT ----
@app.post("/trigger_capture")
async def trigger_capture(auth=Depends(require_secret)):
    async with app.state.lock:
        app.state.capture_requested = True
    return {"ok": True}

@app.get("/barrier_command")
async def consume_barrier_command(auth=Depends(require_secret)):
    async with app.state.lock:
        cmd = app.state.barrier_command
        if cmd == "open":
            app.state.barrier_command = "close"
    return {"command": cmd}

# ---- AI Worker ----
@app.get("/capture_request")
async def consume_capture_request(auth=Depends(require_secret)):
    async with app.state.lock:
        should = app.state.capture_requested
        if should:
            app.state.capture_requested = False
    return {"capture": should}

@app.post("/check_in", status_code=201)
async def check_in(payload: PlatePayload, auth=Depends(require_secret)):
    plate = payload.plate_text.strip().upper()
    time_in = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        # Chặn check-in trùng (nếu muốn)
        existing = cur.execute(
            "SELECT 1 FROM sessions WHERE plate_text=? AND status='CHECKED_IN' LIMIT 1",
            (plate,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Already checked in")

        session_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO sessions (session_id, plate_text, time_in, status) VALUES (?, ?, ?, ?)",
            (session_id, plate, time_in, "CHECKED_IN")
        )
    async with app.state.lock:
        app.state.barrier_command = "open"
    return {"ok": True, "session_id": session_id}

@app.post("/check_out")
async def check_out(payload: PlatePayload, auth=Depends(require_secret)):
    plate = payload.plate_text.strip().upper()
    time_out = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        res = cur.execute("""
            SELECT * FROM sessions
            WHERE plate_text=? AND status='CHECKED_IN'
            ORDER BY time_in DESC LIMIT 1
        """, (plate,)).fetchone()

        if not res:
            raise HTTPException(status_code=404, detail="Vehicle not found or already checked out")

        # TODO: tính phí fee ở đây nếu cần
        cur.execute(
            "UPDATE sessions SET time_out=?, status='CHECKED_OUT' WHERE session_id=?",
            (time_out, res["session_id"])
        )

    async with app.state.lock:
        app.state.barrier_command = "open"
    return {"ok": True, "session_id": res["session_id"]}

# ---- Monitor ----
@app.get("/events")
async def list_events(limit: int = 50, auth=Depends(require_secret)):
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM sessions ORDER BY time_in DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return {"events": [dict(r) for r in rows]}
