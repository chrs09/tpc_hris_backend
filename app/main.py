import logging
import os
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.services.slack_service import send_error_alert, send_response_alert
from app.api import (
    health,
    auth,
    employees,
    attendance,
    dashboard,
    reminder,
    users,
    map,
    debugger,
    leave,
    overtime_request,
    department_head,
    employee_module_access,
    cash_advance_request,
    cash_advance_settings,
)
from app.api.payroll import overtime_approval, payroll_deductions
from app.api import schedule_template as schedule_template_router
from app.api.driver import trips
from app.api.admin import trips as admin_trips
from app.api.admin import stores as stores
from app.api.admin import dispatch as admin_dispatch
from app.api.admin import settings as admin_settings
from app.api.admin.applicants import router as admin_applicants_router
from app.api.public.public_applicant import router as public_applicant_router
from app.api.public.applicant_onboarding import router as applicant_onboarding_router
from app.api.public.applicant_questions import router as applicant_questions_router
from app.api.admin.applicant_questions import router as admin_applicant_questions_router
from app.api.tripProfile import trip_maintenance as trip_maintenance_router
from app.api.office import trips as office_trip_review_router
from app.api import holidays as holiday_router
from app.api.finance import trips as finance_trips_router
from app.api.finance import expenses as finance_expense_router


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


# Any HTTP error response (4xx/5xx) triggers a Slack alert to
# #production-errors -- every status code, not just a curated set. Set
# this to a specific set of codes instead of `None` if the channel ever
# gets too noisy and some codes (e.g. 401 wrong-password spam) need to
# be excluded.
ALERT_STATUS_CODES = None


def _should_alert(status_code: int) -> bool:
    if ALERT_STATUS_CODES is None:
        return status_code >= 400
    return status_code in ALERT_STATUS_CODES


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Replicates FastAPI's default HTTPException handling exactly
    (same response shape/headers for every status code), but also posts
    a Slack alert for every error status."""
    if _should_alert(exc.status_code):
        send_response_alert(
            method=request.method,
            url=str(request.url),
            status_code=exc.status_code,
            detail=exc.detail,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """FastAPI/Pydantic request validation failures -- always a 422.
    Replicates the default response shape, plus a Slack alert."""
    errors = jsonable_encoder(exc.errors())

    if _should_alert(422):
        send_response_alert(
            method=request.method,
            url=str(request.url),
            status_code=422,
            detail=errors,
        )

    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("UNHANDLED SERVER ERROR")
    logger.error("URL: %s %s", request.method, request.url)
    traceback.print_exc()

    # Best-effort Slack alert to #production-errors -- send_error_alert
    # never raises, so a broken/misconfigured webhook can never turn
    # into a second failure on top of the original error being handled.
    send_error_alert(
        method=request.method,
        url=str(request.url),
        exc=exc,
        traceback_text=traceback.format_exc(),
    )

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
    "https://portal.tytanprime.net",
    "http://portal.tytanprime.net",
    "http://192.168.1.141",

    # Vercel
    "https://tpc-hris-frontend.vercel.app",
    "https://tpcportal.tytanprime.net",
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
        r"|^https://.*\.vercel\.app$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(map.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reminder.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(leave.router, prefix="/api")
app.include_router(overtime_request.router, prefix="/api")
app.include_router(department_head.router, prefix="/api")
app.include_router(employee_module_access.router, prefix="/api")
app.include_router(cash_advance_request.router, prefix="/api")
app.include_router(cash_advance_settings.router, prefix="/api")
app.include_router(overtime_approval.router, prefix="/api")
app.include_router(payroll_deductions.router, prefix="/api")
app.include_router(schedule_template_router.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(trip_maintenance_router.router, prefix="/api")

app.include_router(admin_trips.router, prefix="/api")
app.include_router(stores.router, prefix="/api")
app.include_router(admin_dispatch.router, prefix="/api")
app.include_router(admin_settings.router, prefix="/api")
app.include_router(admin_applicants_router)
app.include_router(admin_applicant_questions_router)

app.include_router(public_applicant_router)
app.include_router(applicant_onboarding_router)
app.include_router(applicant_questions_router)

# finance
app.include_router(finance_trips_router.router, prefix="/api")  # Add this line to include the finance trips router
app.include_router(finance_expense_router.router, prefix="/api")  # Add this line to include the finance expense router

# office
app.include_router(office_trip_review_router.router, prefix="/api")  # Add this line to include the office trip review router

app.include_router(holiday_router.router, prefix="/api")  # Add this line to include the holiday router

# debugger
app.include_router(debugger.router, prefix="/api")


if settings.FILE_STORAGE == "local":
    os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)

    app.mount(
        "/uploads",
        StaticFiles(directory=settings.UPLOAD_FOLDER),
        name="uploads",
    )
