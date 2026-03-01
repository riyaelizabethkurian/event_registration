from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import secrets

app = FastAPI(title="Event Registration System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── DATABASE ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect("events.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT DEFAULT '',
            venue TEXT DEFAULT '',
            date TEXT DEFAULT '',
            time TEXT DEFAULT '',
            total_seats INTEGER NOT NULL,
            available_seats INTEGER NOT NULL,
            food_options TEXT DEFAULT '',
            stay_available INTEGER DEFAULT 0,
            topics TEXT DEFAULT '',
            guests TEXT DEFAULT '',
            speakers TEXT DEFAULT '',
            price REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            booking_ref TEXT UNIQUE NOT NULL,
            participants INTEGER NOT NULL,
            participant_details TEXT NOT NULL,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ── MODELS ────────────────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title: str
    type: str
    description: Optional[str] = ""
    venue: Optional[str] = ""
    date: Optional[str] = ""
    time: Optional[str] = ""
    total_seats: int
    food_options: Optional[str] = ""
    stay_available: Optional[int] = 0
    topics: Optional[str] = ""
    guests: Optional[str] = ""
    speakers: Optional[str] = ""
    price: Optional[float] = 0

class BookingCreate(BaseModel):
    event_id: int
    participants: int
    participant_details: str  # JSON string

# ── PAGES ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ── EVENT ROUTES ──────────────────────────────────────────────────────────────

@app.get("/api/events")
async def get_events():
    conn = get_db()
    events = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(e) for e in events]

@app.get("/api/events/{event_id}")
async def get_event(event_id: int):
    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return dict(event)

@app.post("/api/events")
async def create_event(data: EventCreate):
    conn = get_db()
    conn.execute("""
        INSERT INTO events (title, type, description, venue, date, time,
        total_seats, available_seats, food_options, stay_available,
        topics, guests, speakers, price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data.title, data.type, data.description, data.venue, data.date,
          data.time, data.total_seats, data.total_seats, data.food_options,
          data.stay_available, data.topics, data.guests, data.speakers, data.price))
    conn.commit()
    conn.close()
    return {"message": "Event created successfully"}

@app.put("/api/events/{event_id}")
async def update_event(event_id: int, data: EventCreate):
    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    conn.execute("""
        UPDATE events SET title=?, type=?, description=?, venue=?, date=?,
        time=?, total_seats=?, food_options=?, stay_available=?,
        topics=?, guests=?, speakers=?, price=? WHERE id=?
    """, (data.title, data.type, data.description, data.venue, data.date,
          data.time, data.total_seats, data.food_options, data.stay_available,
          data.topics, data.guests, data.speakers, data.price, event_id))
    conn.commit()
    conn.close()
    return {"message": "Event updated successfully"}

@app.delete("/api/events/{event_id}")
async def delete_event(event_id: int):
    conn = get_db()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return {"message": "Event deleted"}

# ── BOOKING ROUTES ────────────────────────────────────────────────────────────

@app.get("/api/bookings")
async def get_all_bookings():
    conn = get_db()
    bookings = conn.execute("""
        SELECT b.*, e.title as event_title, e.date, e.venue, e.type
        FROM bookings b JOIN events e ON b.event_id = e.id
        ORDER BY b.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(b) for b in bookings]

@app.post("/api/bookings")
async def create_booking(data: BookingCreate):
    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (data.event_id,)).fetchone()

    if not event:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")

    if event["available_seats"] < data.participants:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Only {event['available_seats']} seats available")

    booking_ref = "EVT" + secrets.token_hex(4).upper()

    conn.execute("""
        INSERT INTO bookings (event_id, booking_ref, participants, participant_details)
        VALUES (?, ?, ?, ?)
    """, (data.event_id, booking_ref, data.participants, data.participant_details))

    conn.execute(
        "UPDATE events SET available_seats = available_seats - ? WHERE id = ?",
        (data.participants, data.event_id)
    )
    conn.commit()
    conn.close()

    return {
        "message": "Booking confirmed!",
        "booking_ref": booking_ref,
        "event_title": event["title"],
        "participants": data.participants
    }
