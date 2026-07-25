"""
One-time backfill script.

Run this ONCE after the migration is applied, and BEFORE you switch
any endpoint logic to rely on trip_rate_profile_id.

What it does:
1. For every TripRateProfile, derives `code` from the leading segment
   of `profile_name` (e.g. "DP - Core A (No Helper)" -> "DP")
   -- REVIEW the printed mapping before confirming, in case any
   profile_name doesn't follow the "CODE - Description" pattern.
2. For every Store, resolves `trip_rate_profile_id` by matching its
   legacy `profile` string against the newly-set `code`.

Usage:
    python -m scripts.backfill_trip_rate_profile_linkage
"""

from app.core.database import SessionLocal

# Import the full models package first so every model class referenced by
# relationship() strings (e.g. "TripFinanceReview") is registered with
# SQLAlchemy's declarative registry before any query runs. Standalone
# scripts don't go through your app's normal startup import chain, so
# without this, mapper configuration fails with InvalidRequestError.
import app.models  # noqa: F401

from app.models.TripRate import TripRateProfile
from app.models.stores import Store
from app.models.trip_finance_review import TripFinanceReview

def run():
    db = SessionLocal()

    try:
        # ---- 1. Backfill TripRateProfile.code ----
        profiles = db.query(TripRateProfile).all()

        print("\n--- TripRateProfile code assignment ---")

        for profile in profiles:
            if profile.code:
                print(f"  [skip] id={profile.id} already has code={profile.code}")
                continue

            derived_code = profile.profile_name.split(" - ")[0].strip().upper()
            profile.code = derived_code

            print(
                f"  id={profile.id} profile_name='{profile.profile_name}' "
                f"-> code='{derived_code}'"
            )

        db.flush()

        # ---- 2. Backfill Store.trip_rate_profile_id ----
        code_to_profile = {p.code: p for p in profiles if p.code}

        stores = db.query(Store).all()

        print("\n--- Store trip_rate_profile_id assignment ---")

        unmatched = []

        for store in stores:
            if store.trip_rate_profile_id:
                print(f"  [skip] store id={store.id} already linked")
                continue

            store_code = (store.profile or "").strip().upper()
            matched = code_to_profile.get(store_code)

            if not matched:
                unmatched.append(store)
                print(
                    f"  [UNMATCHED] store id={store.id} name='{store.name}' "
                    f"profile='{store.profile}' -- no matching TripRateProfile.code"
                )
                continue

            store.trip_rate_profile_id = matched.id
            print(
                f"  store id={store.id} name='{store.name}' profile='{store.profile}' "
                f"-> trip_rate_profile_id={matched.id}"
            )

        db.commit()

        print(f"\nDone. {len(unmatched)} store(s) left unmatched.")

        if unmatched:
            print(
                "Review these manually -- they will fall back to their legacy "
                "`required_helper` value until trip_rate_profile_id is set."
            )

    finally:
        db.close()


if __name__ == "__main__":
    run()