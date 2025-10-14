# backend_server/app.py
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

app = FastAPI(title="Parking System Backend", version="1.2.0")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON;")
        con.execute("PRAGMA journal_mode=WAL;")

        con.execute("""
        CREATE TABLE IF NOT EXISTS cards (
          card_id TEXT PRIMARY KEY,
          is_guest BOOLEAN NOT NULL
        );""")

        con.execute("""
        CREATE TABLE IF NOT EXISTS registered_users (
          user_id TEXT PRIMARY KEY,
          full_name TEXT NOT NULL,
          card_id TEXT NOT NULL UNIQUE,
          other_info TEXT,
          FOREIGN KEY (card_id) REFERENCES cards(card_id)
        );""")

        con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
          session_id TEXT PRIMARY KEY,
          plate_text TEXT,
          time_in TEXT NOT NULL,
          time_out TEXT,
          card_id TEXT NOT NULL,
          lane TEXT,
          status TEXT NOT NULL,
          fee REAL,
          FOREIGN KEY (card_id) REFERENCES cards(card_id)
        );""")

        con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_card_status ON sessions(card_id, status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_plate_status ON sessions(plate_text, status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_time_in ON sessions(time_in)")

init_db()

def require_secret(x_secret: Optional[str] = Header(None, alias="X-Secret")):
    if x_secret != SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ---- App-scoped state ----
app.state.capture_queue = []
app.state.barrier_command = "close"
app.state.lock = asyncio.Lock()

# ---- Models ----
class CardPayload(BaseModel):
    card_id: str
    lane: Optional[str] = None

class PlateUpdatePayload(BaseModel):
    session_id: str
    plate_text: str

# ---- API for ESP32 ----
@app.post("/check-in", status_code=201)
async def initiate_check_in(payload: CardPayload, auth=Depends(require_secret)):
    card_id = payload.card_id.strip()
    time_in = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON;")
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        card = cur.execute("SELECT * FROM cards WHERE card_id=?", (card_id,)).fetchone()
        if not card:
            raise HTTPException(status_code=404, detail=f"Card '{card_id}' not found.")

        active_session = cur.execute(
            "SELECT 1 FROM sessions WHERE card_id=? AND status IN ('PENDING_PLATE', 'CHECKED_IN')",
            (card_id,)
        ).fetchone()
        if active_session:
            raise HTTPException(status_code=409, detail=f"Card '{card_id}' is already checked in.")

        session_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO sessions (session_id, time_in, card_id, lane, status) VALUES (?, ?, ?, ?, ?)",
            (session_id, time_in, card_id, payload.lane, "PENDING_PLATE")
        )

    async with app.state.lock:
        app.state.capture_queue.append(session_id)

    return {"ok": True, "session_id": session_id, "message": "Session created. Awaiting plate capture."}

@app.post("/check-out")
async def process_check_out(payload: CardPayload, auth=Depends(require_secret)):
    card_id = payload.card_id.strip()
    time_out = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON;")
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        session = cur.execute(
            "SELECT * FROM sessions WHERE card_id=? AND status='CHECKED_IN' ORDER BY time_in DESC LIMIT 1",
            (card_id,)
        ).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="No active checked-in session found for this card.")

        session_id = session["session_id"]
        cur.execute(
            "UPDATE sessions SET time_out=?, status='CHECKED_OUT' WHERE session_id=?",
            (time_out, session_id)
        )

    async with app.state.lock:
        app.state.barrier_command = "open"

    return {"ok": True, "session_id": session_id, "message": "Check-out successful."}

@app.get("/barrier-command")
async def consume_barrier_command(auth=Depends(require_secret)):
    async with app.state.lock:
        cmd = app.state.barrier_command
        if cmd == "open":
            app.state.barrier_command = "close"
    return {"command": cmd}

# ---- API for AI Worker ----
@app.get("/capture-task")
async def get_capture_task(auth=Depends(require_secret)):
    session_id = None
    async with app.state.lock:
        if app.state.capture_queue:
            session_id = app.state.capture_queue.pop(0)

    if session_id:
        return {"task": "capture_plate", "session_id": session_id}
    else:
        return {"task": "none"}

@app.post("/update-plate")
async def update_session_plate(payload: PlateUpdatePayload, auth=Depends(require_secret)):
    session_id = payload.session_id
    plate_text = payload.plate_text.strip().upper()

    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON;")
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        session = cur.execute(
            "SELECT * FROM sessions WHERE session_id=? AND status='PENDING_PLATE'",
            (session_id,)
        ).fetchone()

        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found or not pending plate update.")

        cur.execute(
            "UPDATE sessions SET plate_text=?, status='CHECKED_IN' WHERE session_id=?",
            (plate_text, session_id)
        )

    async with app.state.lock:
        app.state.barrier_command = "open"

    return {"ok": True, "message": f"Plate for session {session_id} updated."}

# ---- API for Monitoring ----
@app.get("/events")
async def list_events(limit: int = 50, auth=Depends(require_secret)):
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM sessions ORDER BY time_in DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return {"events": [dict(r) for r in rows]}