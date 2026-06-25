from fastapi import APIRouter, Request
from pathlib import Path
from datetime import datetime

router = APIRouter(
    prefix="/debug",
    tags=["Debug"],
)

LOG_FILE = Path(__file__).resolve().parent.parent.parent / "mobile_debug.log"

# Counter for numbering log entries
log_counter = 0

# Clear previous logs whenever the backend starts
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write(
        "============================================================\n"
        "                MOBILE DEBUG LOGGER\n"
        "============================================================\n"
        f"SERVER STARTED : {datetime.utcnow().isoformat()} UTC\n"
        "============================================================\n\n"
    )


@router.post("/mobile-log")
async def mobile_log(request: Request):
    global log_counter

    payload = await request.json()
    log_counter += 1

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write("=" * 70 + "\n")
        f.write(f"LOG #{log_counter}\n")
        f.write(f"SERVER TIME : {datetime.utcnow().isoformat()} UTC\n")

        # Highlight important fields first
        if "type" in payload:
            f.write(f"TYPE        : {payload['type']}\n")

        if "timestamp" in payload:
            f.write(f"CLIENT TIME : {payload['timestamp']}\n")

        f.write("=" * 70 + "\n")

        # Print remaining payload fields
        for key, value in payload.items():
            if key in ["type", "timestamp"]:
                continue

            f.write(f"{key.upper():18}: {value}\n")

        f.write("=" * 70 + "\n")

    return {"success": True}