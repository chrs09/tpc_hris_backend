from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.finance_expense import FinanceExpense
from app.models.user import User

from app.schemas.finance_expense import (
    FinanceExpenseResponse,
)

from app.services.file_service import FileService
from app.utils.response import api_response


router = APIRouter(
    prefix="/finance/expenses",
    tags=["Finance - Expenses"],
)


# =========================================================
# CONSTANTS
# =========================================================

ALLOWED_UNITS = {
    "Piece",
    "Unit",
    "Set",
    "Box",
    "Pack",
    "Bottle",
    "Can",
    "Liter",
    "Meter",
    "Kilogram",
    "Gram",
    "Hour",
    "Day",
    "Trip",
    "Job",
    "Other",
}

ALLOWED_STATUS = {
    "Pending",
    "Paid",
    "Cancelled",
}


# =========================================================
# HELPERS
# =========================================================

def decimal_to_float(value):
    if value is None:
        return None

    if isinstance(value, Decimal):
        return float(value)

    return value


def serialize_expense(expense: FinanceExpense):
    return {
        "id": expense.id,

        "encoded_date": expense.encoded_date,

        "posting_period": expense.posting_period,

        "date": expense.date,

        "po_number": expense.po_number,

        "supplier": expense.supplier,

        "receipt_number": expense.receipt_number,

        "receipt_image_url": expense.receipt_image_url,

        "qty": decimal_to_float(expense.qty),

        "unit": expense.unit,

        "particulars": expense.particulars,

        "unit_price": decimal_to_float(
            expense.unit_price
        ),

        "amount": decimal_to_float(
            expense.amount
        ),

        "responsible": expense.responsible,

        "additional_details": expense.additional_details,

        "requested_by": expense.requested_by,

        "received_by": expense.received_by,

        "category": expense.category,

        "account": expense.account,

        "notes": expense.notes,

        "date_countered": expense.date_countered,

        "counter_number": expense.counter_number,

        "date_paid": expense.date_paid,

        "bank": expense.bank,

        "check_number": expense.check_number,

        "check_amount": decimal_to_float(
            expense.check_amount
        ),

        "receipt_number_2": expense.receipt_number_2,

        "status": expense.status,

        "ap": decimal_to_float(expense.ap),

        "remarks": expense.remarks,

        "created_by_user_id": expense.created_by_user_id,

        "updated_by_user_id": expense.updated_by_user_id,

        "created_at": expense.created_at,

        "updated_at": expense.updated_at,
    }


def validate_unit(unit: Optional[str]):
    if unit and unit not in ALLOWED_UNITS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid unit. Allowed units: {', '.join(sorted(ALLOWED_UNITS))}",
        )


def validate_status(status: Optional[str]):
    if status and status not in ALLOWED_STATUS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status. "
                "Allowed statuses: Pending, Paid, Cancelled"
            ),
        )


def calculate_amount(
    qty,
    unit_price,
):
    if qty is None or unit_price is None:
        return None

    return Decimal(str(qty)) * Decimal(str(unit_price))


# =========================================================
# GET ALL EXPENSES
# =========================================================

@router.get("/")
def get_expenses(
    search: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    account: Optional[str] = Query(None),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(FinanceExpense)

    if search:
        search_value = f"%{search.strip()}%"

        query = query.filter(
            (
                FinanceExpense.receipt_number.ilike(
                    search_value
                )
                |
                FinanceExpense.supplier.ilike(
                    search_value
                )
                |
                FinanceExpense.particulars.ilike(
                    search_value
                )
                |
                FinanceExpense.po_number.ilike(
                    search_value
                )
                |
                FinanceExpense.responsible.ilike(
                    search_value
                )
            )
        )

    if supplier:
        query = query.filter(
            FinanceExpense.supplier == supplier
        )

    if category:
        query = query.filter(
            FinanceExpense.category == category
        )

    if status:
        query = query.filter(
            FinanceExpense.status == status
        )

    if account:
        query = query.filter(
            FinanceExpense.account == account
        )

    expenses = (
        query
        .order_by(
            FinanceExpense.date.desc(),
            FinanceExpense.id.desc(),
        )
        .all()
    )

    response = [
        serialize_expense(expense)
        for expense in expenses
    ]

    return api_response(response)


# =========================================================
# GET EXPENSE DETAIL
# =========================================================

@router.get("/{expense_id}")
def get_expense(
    expense_id: int,

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = (
        db.query(FinanceExpense)
        .filter(
            FinanceExpense.id == expense_id
        )
        .first()
    )

    if not expense:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    return api_response(
        serialize_expense(expense)
    )


# =========================================================
# CREATE EXPENSE
# =========================================================

@router.post("/", status_code=201)
async def create_expense(
    posting_period: Optional[str] = Form(None),
    date: Optional[str] = Form(None),

    po_number: Optional[str] = Form(None),
    supplier: Optional[str] = Form(None),
    receipt_number: Optional[str] = Form(None),

    qty: Optional[float] = Form(1),
    unit: Optional[str] = Form("Piece"),
    particulars: Optional[str] = Form(None),
    unit_price: Optional[float] = Form(None),

    responsible: Optional[str] = Form(None),
    additional_details: Optional[str] = Form(None),
    requested_by: Optional[str] = Form(None),
    received_by: Optional[str] = Form(None),

    category: Optional[str] = Form(None),
    account: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),

    date_countered: Optional[str] = Form(None),
    counter_number: Optional[str] = Form(None),

    date_paid: Optional[str] = Form(None),
    bank: Optional[str] = Form(None),
    check_number: Optional[str] = Form(None),
    check_amount: Optional[float] = Form(None),
    receipt_number_2: Optional[str] = Form(None),

    status: Optional[str] = Form("Pending"),
    ap: Optional[float] = Form(None),
    remarks: Optional[str] = Form(None),

    receipt_image: Optional[UploadFile] = File(None),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # -----------------------------------------
    # VALIDATION
    # -----------------------------------------

    validate_unit(unit)
    validate_status(status)

    # -----------------------------------------
    # PARSE DATES
    # -----------------------------------------

    parsed_date = None

    if date:
        try:
            parsed_date = datetime.strptime(
                date,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD",
            )

    parsed_date_countered = None

    if date_countered:
        try:
            parsed_date_countered = datetime.strptime(
                date_countered,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date_countered format. Use YYYY-MM-DD",
            )

    parsed_date_paid = None

    if date_paid:
        try:
            parsed_date_paid = datetime.strptime(
                date_paid,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date_paid format. Use YYYY-MM-DD",
            )

    # -----------------------------------------
    # CALCULATE AMOUNT
    # -----------------------------------------

    amount = calculate_amount(
        qty,
        unit_price,
    )

    # -----------------------------------------
    # CREATE EXPENSE
    # -----------------------------------------

    expense = FinanceExpense(
        encoded_date=datetime.utcnow(),

        posting_period=posting_period,

        date=parsed_date,

        po_number=po_number,

        supplier=supplier,

        receipt_number=receipt_number,

        qty=qty,

        unit=unit,

        particulars=particulars,

        unit_price=unit_price,

        amount=amount,

        responsible=responsible,

        additional_details=additional_details,

        requested_by=requested_by,

        received_by=received_by,

        category=category,

        account=account,

        notes=notes,

        date_countered=parsed_date_countered,

        counter_number=counter_number,

        date_paid=parsed_date_paid,

        bank=bank,

        check_number=check_number,

        check_amount=check_amount,

        receipt_number_2=receipt_number_2,

        status=status or "Pending",

        ap=ap,

        remarks=remarks,

        created_by_user_id=current_user.id,

        updated_by_user_id=current_user.id,
    )

    db.add(expense)
    db.flush()

    # -----------------------------------------
    # RECEIPT IMAGE
    # -----------------------------------------

    if receipt_image:
        file_service = FileService()

        file_url = file_service.upload(
            receipt_image,
            f"finance/{expense.id}",
        )

        expense.receipt_image_url = file_url

    db.commit()
    db.refresh(expense)

    return api_response(
        serialize_expense(expense)
    )


# =========================================================
# UPDATE EXPENSE
# =========================================================

@router.patch("/{expense_id}")
async def update_expense(
    expense_id: int,

    posting_period: Optional[str] = Form(None),
    date: Optional[str] = Form(None),

    po_number: Optional[str] = Form(None),
    supplier: Optional[str] = Form(None),
    receipt_number: Optional[str] = Form(None),

    qty: Optional[float] = Form(None),
    unit: Optional[str] = Form(None),
    particulars: Optional[str] = Form(None),
    unit_price: Optional[float] = Form(None),

    responsible: Optional[str] = Form(None),
    additional_details: Optional[str] = Form(None),
    requested_by: Optional[str] = Form(None),
    received_by: Optional[str] = Form(None),

    category: Optional[str] = Form(None),
    account: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),

    date_countered: Optional[str] = Form(None),
    counter_number: Optional[str] = Form(None),

    date_paid: Optional[str] = Form(None),
    bank: Optional[str] = Form(None),
    check_number: Optional[str] = Form(None),
    check_amount: Optional[float] = Form(None),
    receipt_number_2: Optional[str] = Form(None),

    status: Optional[str] = Form(None),
    ap: Optional[float] = Form(None),
    remarks: Optional[str] = Form(None),

    receipt_image: Optional[UploadFile] = File(None),

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = (
        db.query(FinanceExpense)
        .filter(
            FinanceExpense.id == expense_id
        )
        .first()
    )

    if not expense:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    validate_unit(unit)
    validate_status(status)

    # -----------------------------------------
    # BASIC FIELDS
    # -----------------------------------------

    if posting_period is not None:
        expense.posting_period = posting_period

    if date is not None:
        try:
            expense.date = datetime.strptime(
                date,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD",
            )

    if po_number is not None:
        expense.po_number = po_number

    if supplier is not None:
        expense.supplier = supplier

    if receipt_number is not None:
        expense.receipt_number = receipt_number

    # -----------------------------------------
    # ITEM
    # -----------------------------------------

    if qty is not None:
        expense.qty = qty

    if unit is not None:
        expense.unit = unit

    if particulars is not None:
        expense.particulars = particulars

    if unit_price is not None:
        expense.unit_price = unit_price

    # Recalculate amount whenever
    # quantity or unit price changes.
    if qty is not None or unit_price is not None:
        expense.amount = calculate_amount(
            expense.qty,
            expense.unit_price,
        )

    # -----------------------------------------
    # ASSIGNMENT
    # -----------------------------------------

    if responsible is not None:
        expense.responsible = responsible

    if additional_details is not None:
        expense.additional_details = additional_details

    if requested_by is not None:
        expense.requested_by = requested_by

    if received_by is not None:
        expense.received_by = received_by

    # -----------------------------------------
    # ACCOUNTING
    # -----------------------------------------

    if category is not None:
        expense.category = category

    if account is not None:
        expense.account = account

    if notes is not None:
        expense.notes = notes

    # -----------------------------------------
    # COUNTERING
    # -----------------------------------------

    if date_countered is not None:
        try:
            expense.date_countered = datetime.strptime(
                date_countered,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid date_countered format. "
                    "Use YYYY-MM-DD"
                ),
            )

    if counter_number is not None:
        expense.counter_number = counter_number

    # -----------------------------------------
    # PAYMENT
    # -----------------------------------------

    if date_paid is not None:
        try:
            expense.date_paid = datetime.strptime(
                date_paid,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid date_paid format. "
                    "Use YYYY-MM-DD"
                ),
            )

    if bank is not None:
        expense.bank = bank

    if check_number is not None:
        expense.check_number = check_number

    if check_amount is not None:
        expense.check_amount = check_amount

    if receipt_number_2 is not None:
        expense.receipt_number_2 = receipt_number_2

    # -----------------------------------------
    # AP
    # -----------------------------------------

    if status is not None:
        expense.status = status

    if ap is not None:
        expense.ap = ap

    if remarks is not None:
        expense.remarks = remarks

    # -----------------------------------------
    # RECEIPT IMAGE
    # -----------------------------------------

    if receipt_image:
        file_service = FileService()

        file_url = file_service.upload(
            receipt_image,
            f"finance/{expense.id}",
        )

        expense.receipt_image_url = file_url

    # -----------------------------------------
    # AUDIT
    # -----------------------------------------

    expense.updated_by_user_id = current_user.id
    expense.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(expense)

    return api_response(
        serialize_expense(expense)
    )


# =========================================================
# DELETE EXPENSE
# =========================================================

@router.delete("/{expense_id}")
def delete_expense(
    expense_id: int,

    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = (
        db.query(FinanceExpense)
        .filter(
            FinanceExpense.id == expense_id
        )
        .first()
    )

    if not expense:
        raise HTTPException(
            status_code=404,
            detail="Expense not found",
        )

    db.delete(expense)
    db.commit()

    return api_response(
        {
            "message": "Expense deleted successfully"
        }
    )