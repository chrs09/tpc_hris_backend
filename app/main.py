import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api import health, auth, employees, attendance, dashboard, reminder, users
from app.api.driver import trips
from app.api.admin import trips as admin_trips
from app.api.admin import stores
from app.api.admin.applicants import router as admin_applicants_router
from app.api.public.public_applicant import router as public_applicant_router
from app.api.public.applicant_onboarding import router as applicant_onboarding_router
from app.api.public.applicant_questions import router as applicant_questions_router
from app.api.admin.applicant_questions import router as admin_applicant_questions_router

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

logger = logging.getLogger("main")


app = FastAPI(
    title=settings.APP_NAME,
    description="A simple HRIS API built with FastAPI",
    version="1.0.0",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("UNHANDLED SERVER ERROR")
    logger.error("URL: %s %s", request.method, request.url)
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("REQUEST: %s %s", request.method, request.url)
    response = await call_next(request)
    logger.info("STATUS: %s", response.status_code)
    return response


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
    allow_origin_regex=(
        r"^https?://("
        r"localhost|"
        r"127\.0\.0\.1|"
        r"192\.168\.\d+\.\d+|"
        r"10\.\d+\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+"
        r")(:\d+)?$"
    ),
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

app.include_router(trips.router, prefix="/api")

app.include_router(admin_trips.router, prefix="/api")
app.include_router(stores.router, prefix="/api")
app.include_router(admin_applicants_router)
app.include_router(admin_applicant_questions_router)

app.include_router(public_applicant_router)
app.include_router(applicant_onboarding_router)
app.include_router(applicant_questions_router)


if settings.FILE_STORAGE == "local":
    os.makedirs("uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
