"""
One-time setup script.

Resets TripRateProfile data to match the 5 real store categories
(DP, KD, KA, PUP, WS), per the reference table provided:

    DP   - Core A (No Helper)  - 0 helpers
    KD   - Core B (No Helper)  - 0 helpers
    KA   - Key Accounts        - 2 helpers
    PUP  - Core C (No Helper)  - 0 helpers
    WS   - Wholesaler          - 2 helpers

Safety: does NOT delete any existing rows (in case Trip records already
reference them via trip_rate_profile_id). Instead:
  - Renames/repurposes the 3 existing rows in place (keeps their IDs)
  - Creates 2 new rows for the remaining codes

IMPORTANT: rate fields (driver_first_trip_rate, driver_next_trip_rate,
helper_first_trip_rate, helper_next_trip_rate) are set to 0 as
placeholders. Update these with real values afterward before this
goes live for actual payroll/trip rate calculations.

Usage:
    python -m scripts.setup_trip_rate_profiles
"""

from app.core.database import SessionLocal

import app.models  # noqa: F401  -- ensures full model registry is loaded

from app.models.TripRate import TripRateProfile
from app.models.trip_finance_review import TripFinanceReview


# id -> new values, for the 3 existing rows we're repurposing.
# Adjust the `id` values below if your actual row IDs differ.
EXISTING_ROW_UPDATES = {
    1: {"code": "DP", "profile_name": "DP - Core A (No Helper)", "helper_count": 0},
    2: {"code": "KD", "profile_name": "KD - Core B (No Helper)", "helper_count": 0},
    3: {"code": "WS", "profile_name": "WS - Wholesaler", "helper_count": 2},
}

# Brand-new rows to create for the remaining codes.
NEW_ROWS = [
    {
        "code": "KA",
        "profile_name": "KA - Key Accounts",
        "helper_count": 2,
        "driver_first_trip_rate": 0,
        "driver_next_trip_rate": 0,
        "helper_first_trip_rate": 0,
        "helper_next_trip_rate": 0,
    },
    {
        "code": "PUP",
        "profile_name": "PUP - Core C (No Helper)",
        "helper_count": 0,
        "driver_first_trip_rate": 0,
        "driver_next_trip_rate": 0,
        "helper_first_trip_rate": 0,
        "helper_next_trip_rate": 0,
    },
]


def run():
    db = SessionLocal()

    try:
        print("\n--- Repurposing existing TripRateProfile rows ---")

        for row_id, updates in EXISTING_ROW_UPDATES.items():
            profile = (
                db.query(TripRateProfile)
                .filter(TripRateProfile.id == row_id)
                .first()
            )

            if not profile:
                print(f"  [WARNING] id={row_id} not found, skipping.")
                continue

            old_name = profile.profile_name
            profile.code = updates["code"]
            profile.profile_name = updates["profile_name"]
            profile.helper_count = updates["helper_count"]

            print(
                f"  id={row_id} '{old_name}' -> "
                f"code='{updates['code']}' name='{updates['profile_name']}' "
                f"helper_count={updates['helper_count']}"
            )

        print("\n--- Creating new TripRateProfile rows ---")

        for new_row in NEW_ROWS:
            existing = (
                db.query(TripRateProfile)
                .filter(TripRateProfile.code == new_row["code"])
                .first()
            )

            if existing:
                print(f"  [skip] code='{new_row['code']}' already exists.")
                continue

            profile = TripRateProfile(**new_row)
            db.add(profile)

            print(
                f"  + code='{new_row['code']}' name='{new_row['profile_name']}' "
                f"helper_count={new_row['helper_count']}"
            )

        db.commit()

        print("\nDone. Review the 5 rows in your DB/admin panel and fill in")
        print("real trip rate values (currently placeholders of 0).")

    finally:
        db.close()


if __name__ == "__main__":
    run()