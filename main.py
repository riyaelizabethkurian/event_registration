from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import sqlite3
import os
import secrets

app = FastAPI(title="EventFlow Pro")

# Setup directories
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

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
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, email TEXT UNIQUE, password TEXT, role TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, type TEXT, description TEXT, venue TEXT,
        date TEXT, time TEXT, total_seats INTEGER, available_seats INTEGER,
        stay_available INTEGER, topics TEXT,
        guests TEXT, speakers TEXT, price REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, booking_ref TEXT, 
        participants INTEGER, participant_details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()

init_db()

# ── MODELS ────────────────────────────────────────────────────────────────────

class UserSignup(BaseModel):
    username: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class EventCreate(BaseModel):
    title: str
    type: str
    description: Optional[str] = ""
    venue: Optional[str] = ""
    date: Optional[str] = ""
    time: Optional[str] = ""
    total_seats: int
    stay_available: Optional[int] = 0
    topics: Optional[str] = ""
    guests: Optional[str] = ""
    speakers: Optional[str] = ""
    price: Optional[float] = 0

class BookingCreate(BaseModel):
    event_id: int
    name: str
    phone: str
    email: EmailStr
    food_preference: str

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})

@app.post("/api/signup")
async def signup(data: UserSignup):
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, email, password, role) VALUES (?,?,?,?)",
                     (data.username, data.email, data.password, data.role))
        conn.commit()
        return {"role": data.role}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email exists")
    finally: conn.close()

@app.post("/api/login")
async def login(data: UserLogin):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (data.email,)).fetchone()
    conn.close()
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"role": user["role"]}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, role: str = "user"):
    conn = get_db()
    events = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    bookings = []
    if role == 'admin':
        bookings = conn.execute("SELECT b.*, e.title as event_title FROM bookings b JOIN events e ON b.event_id = e.id").fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "role": role, "events": events, "bookings": bookings})

@app.post("/api/events")
async def create_event(data: EventCreate):
    conn = get_db()
    conn.execute("""INSERT INTO events (title, type, description, venue, date, time, total_seats, 
        available_seats, stay_available, topics, guests, speakers, price) 
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
        (data.title, data.type, data.description, data.venue, data.date, data.time, 
         data.total_seats, data.total_seats, data.stay_available, 
         data.topics, data.guests, data.speakers, data.price))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/book")
async def book_event(data: BookingCreate):
    conn = get_db()
    event = conn.execute("SELECT available_seats FROM events WHERE id = ?", (data.event_id,)).fetchone()
    if event and event['available_seats'] > 0:
        ref = "REF-" + secrets.token_hex(3).upper()
        details = f"Name: {data.name} | Ph: {data.phone} | Food: {data.food_preference}"
        conn.execute("INSERT INTO bookings (event_id, booking_ref, participants, participant_details) VALUES (?,?,?,?)",
                     (data.event_id, ref, 1, details))
        conn.execute("UPDATE events SET available_seats = available_seats - 1 WHERE id = ?", (data.event_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "ref": ref}
    conn.close()
    raise HTTPException(status_code=400, detail="Sold out")