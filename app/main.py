from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
import os
from app.api import health, auth, employees, attendance, dashboard, reminder, users
from app.api.driver import trips
from app.api.admin import trips as admin_trips
from app.api.admin import stores
from app.api.public.public_applicant import router as public_applicant_router

app = FastAPI(
    title=settings.APP_NAME,
    description="A simple HRIS API built with FastAPI",
    version="1.0.0",
)

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:8000/",
    "http://192.168.1.6:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reminder.router, prefix="/api")
app.include_router(users.router, prefix="/api")
# app.include_router(trip_stops.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(admin_trips.router, prefix="/api")
app.include_router(stores.router, prefix="/api")
if settings.FILE_STORAGE == "local":
    os.makedirs("uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.include_router(public_applicant_router)
