from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import joinedload
from datetime import date
from sqlalchemy.orm import (
    Session,
)

from app.core.database import get_db

from app.core.dependencies import get_current_user

from app.models.user import User

from app.models.dispatch import Dispatch

from app.models.dispatch_item import DispatchItem

from app.models.dispatch_helpers import DispatchHelper
from app.models.employees import Employee
from app.models.TripRate import TripRateProfile
from app.models.vehicle_unit import VehicleUnit

from app.schemas.dispatch import (
    DispatchCreate,
    DispatchResponse,
)

router = APIRouter(
    prefix="/admin/dispatch",
    tags=["Admin Dispatch"],
)

@router.post(
    "",
    response_model=DispatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dispatch(
    payload: DispatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    dispatch = Dispatch(
        plan_date=payload.plan_date,
        created_by=current_user.id,
    )

    db.add(dispatch)
    db.flush()

    for item in payload.items:

        dispatch_item = DispatchItem(
            dispatch_id=dispatch.id,
            shipment_no=item.shipment_no,
            dealer_name=item.dealer_name,
            hauler_name=item.hauler_name,
            driver_id=item.driver_id,
            vehicle_unit_id=item.vehicle_unit_id,
            trip_rate_profile_id=item.trip_rate_profile_id,
            pallets=item.pallets,
            cases=item.cases,
        )

        db.add(dispatch_item)
        db.flush()

        for helper in item.helpers:

            dispatch_helper = DispatchHelper(
                dispatch_item_id=dispatch_item.id,
                helper_id=helper.helper_id,
            )

            db.add(dispatch_helper)

    db.commit()

    db.refresh(dispatch)

    return dispatch

@router.get(
    "",
    response_model=list[DispatchResponse],
)
def get_dispatches(
    plan_date: date | None = None,
    db: Session = Depends(get_db),
):
    query = (
        db.query(Dispatch)
        .options(
            joinedload(Dispatch.items)
            .joinedload(DispatchItem.helpers)
            .joinedload(DispatchHelper.helper),

            joinedload(Dispatch.items)
            .joinedload(DispatchItem.driver),

            joinedload(Dispatch.items)
            .joinedload(DispatchItem.vehicle),

            joinedload(Dispatch.items)
            .joinedload(DispatchItem.trip_rate_profile),
        )
    )

    if plan_date:
        query = query.filter(Dispatch.plan_date == plan_date)

    dispatches = (
        query.order_by(
            Dispatch.plan_date.asc(),
            Dispatch.id.asc(),
        )
        .all()
    )

    return dispatches
