from fastapi import APIRouter, Request
from pathlib import Path
from datetime import datetime
import json

router = APIRouter(
    prefix="/debug",
    tags=["Debug"],
)

LOG_FILE = Path(__file__).resolve().parent.parent.parent / "mobile_debug.log"


@router.post("/mobile-log")
async def mobile_log(request: Request):
    payload = await request.json()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "logged_at": datetime.utcnow().isoformat(),
                    "payload": payload,
                }
            )
            + "\n"
        )

    return {"success": True}