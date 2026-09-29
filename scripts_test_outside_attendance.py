"""TEST ONLY (local DB): records a kiosk time-in for Anna Lou Butal from
~1.2 km outside TPC Yard, the same way the real kiosk does, so it shows
up flagged in the Attendance grid, the dashboard Needs Review card and
the geofence alert bell.

Run from tpc_hris_backend:  venv\\Scripts\\python.exe scripts_test_outside_attendance.py
Delete this file afterwards -- it isn't part of the app.
"""

import io
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core.database import SessionLocal
from app.main import app
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee

db = SessionLocal()
emps = (
    db.query(Employee)
    .filter(Employee.first_name.ilike("%anna%"), Employee.last_name.ilike("%butal%"))
    .all()
)
print("matches:", [(e.id, e.first_name, e.last_name) for e in emps])
if not emps:
    raise SystemExit("Anna Lou Butal not found.")
emp = emps[0]

today = datetime.now(ZoneInfo("Asia/Manila")).date()
existing = (
    db.query(AttendanceRecord)
    .filter(AttendanceRecord.employee_id == emp.id, AttendanceRecord.attendance_date == today)
    .first()
)
if existing and existing.check_in_time:
    raise SystemExit(f"She already has a time-in today (record {existing.id}).")

img = Image.new("RGB", (480, 640), (70, 110, 150))
ImageDraw.Draw(img).text((140, 300), "TEST SELFIE - Anna Lou Butal", fill=(255, 255, 255))
photo = io.BytesIO()
img.save(photo, "JPEG")
photo.seek(0)

client = TestClient(app, raise_server_exceptions=False)
res = client.post(
    "/api/attendance/kiosk/selfie",
    data={
        "employee_id": emp.id,
        "action": "time_in",
        "latitude": 10.345240,
        "longitude": 123.9478,  # ~1.2 km east of TPC Yard (allowed 150 m)
        "address": "TEST - outside assigned area (~1.2 km from TPC Yard)",
    },
    files={"photo": ("anna.jpg", photo, "image/jpeg")},
)
data = res.json()
print("kiosk:", res.status_code, "|", data.get("message"))

db.commit()
record = db.get(AttendanceRecord, data["attendance_id"])
print(
    f"record {record.id} | review: {record.time_in_face_review_status} | "
    f"outside: {record.time_in_outside_geofence} | {record.time_in_geofence_note}"
)
