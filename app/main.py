from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from app.core.config import settings
import os
import traceback

from app.api import health, auth, employees, attendance, dashboard, reminder, users
from app.api.driver import trips
from app.api.admin import trips as admin_trips
from app.api.admin import stores
from app.api.admin.applicants import router as admin_applicants_router
from app.api.public.public_applicant import router as public_applicant_router
from app.api.public.applicant_onboarding import router as applicant_onboarding_router
from app.api.public.applicant_questions import router as applicant_questions_router
from app.api.admin.applicant_questions import router as admin_applicant_questions_router

app = FastAPI(
    title=settings.APP_NAME,
    description="A simple HRIS API built with FastAPI",
    version="1.0.0",
)

# =========================================
# 🔥 GLOBAL ERROR HANDLER (VERY IMPORTANT)
# =========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("\n🔥🔥🔥 UNHANDLED SERVER ERROR 🔥🔥🔥")
    print(f"URL: {request.method} {request.url}")
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),  # send real error to frontend
        },
    )

# =========================================
# (OPTIONAL) REQUEST LOGGER
# =========================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"\n📡 {request.method} {request.url}")
    response = await call_next(request)
    print(f"➡️ STATUS: {response.status_code}")
    return response

# =========================================
# CORS CONFIG
# =========================================
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://18.142.183.226",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# ROUTERS
# =========================================
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reminder.router, prefix="/api")
app.include_router(users.router, prefix="/api")

# DRIVER
app.include_router(trips.router, prefix="/api")

# ADMIN
app.include_router(admin_trips.router, prefix="/api")
app.include_router(stores.router, prefix="/api")
app.include_router(admin_applicants_router)
app.include_router(admin_applicant_questions_router)

# PUBLIC
app.include_router(public_applicant_router)
app.include_router(applicant_onboarding_router)
app.include_router(applicant_questions_router)

# =========================================
# FILE STORAGE
# =========================================
if settings.FILE_STORAGE == "local":
    os.makedirs("uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")