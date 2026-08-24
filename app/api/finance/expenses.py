from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Any
import re
import json

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
from app.models.finance_expense_item import FinanceExpenseItem
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

def generate_expense_number(db: Session) -> str:
    """
    Generate the next expense number.

    Example:
        EXP001
        EXP002
        EXP003
    """

    expenses = (
        db.query(FinanceExpense.expense_number)
        .filter(FinanceExpense.expense_number.isnot(None))
        .all()
    )

    max_number = 0

    for (expense_number,) in expenses:
        if not expense_number:
            continue

        match = re.fullmatch(r"EXP(\d+)", expense_number)

        if match:
            number = int(match.group(1))
            max_number = max(max_number, number)

    next_number = max_number + 1

    return f"EXP{next_number:03d}"

def calculate_posting_period(created_at: datetime) -> str:
    """
    Calculate posting period based on creation date.

    1st–15th:
        YYYY-MM-01 to YYYY-MM-15

    16th–end:
        YYYY-MM-16 to YYYY-MM-last-day
    """

    year = created_at.year
    month = created_at.month

    if created_at.day <= 15:
        return f"{year}-{month:02d}-01 to {year}-{month:02d}-15"

    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    last_day = (next_month - timedelta(days=1)).day

    return (
        f"{year}-{month:02d}-16 "
        f"to {year}-{month:02d}-{last_day:02d}"
    )

def parse_expense_items(items: Optional[str]) -> list[dict[str, Any]]:
    """
    Parse expense items JSON received from the frontend.

    Expected format:

    [
        {
            "particulars": "Printer Ink",
            "qty": 2,
            "unit": "Box",
            "unit_price": 500
        },
        {
            "particulars": "Bond Paper",
            "qty": 5,
            "unit": "Pack",
            "unit_price": 200
        }
    ]
    """

    if not items:
        return []

    try:
        parsed_items = json.loads(items)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid expense items JSON.",
        ) from exc

    if not isinstance(parsed_items, list):
        raise HTTPException(
            status_code=400,
            detail="Expense items must be a list.",
        )

    return parsed_items

def serialize_expense(expense: FinanceExpense):
    return {
        # ==============================
        # EXPENSE INFORMATION
        # ==============================

        "id": expense.id,
        "expense_number": expense.expense_number,

        "encoded_date": expense.encoded_date,
        "posting_period": expense.posting_period,
        "invoice_date": expense.date,

        # ==============================
        # REFERENCE
        # ==============================

        "po_number": expense.po_number,
        "supplier": expense.supplier,
        "invoice_number": expense.receipt_number,

        # ==============================
        # RECEIPT / EXPENSE IMAGE
        # ==============================

        "receipt_image_url": expense.receipt_image_url,

        # ==============================
        # LEGACY ITEM DETAILS
        # ==============================
        # Kept temporarily for compatibility
        # with existing expense records.

        "qty": decimal_to_float(expense.qty),
        "unit": expense.unit,
        "particulars": expense.particulars,

        "unit_price": decimal_to_float(
            expense.unit_price
        ),

        "amount": decimal_to_float(
            expense.amount
        ),

        # ==============================
        # EXPENSE ITEMS
        # ==============================

        "items": [
            {
                "id": item.id,
                "expense_id": item.expense_id,
                "particulars": item.particulars,
                "qty": decimal_to_float(item.qty),
                "unit": item.unit,
                "unit_price": decimal_to_float(
                    item.unit_price
                ),
                "amount": decimal_to_float(
                    item.amount
                ),
            }
            for item in expense.items
        ],

        # ==============================
        # ASSIGNMENT
        # ==============================

        "responsible": expense.responsible,
        "additional_details": expense.additional_details,
        "requested_by": expense.requested_by,
        "received_by": expense.received_by,

        # ==============================
        # ACCOUNTING
        # ==============================

        "category": expense.category,
        "account": expense.account,
        "notes": expense.notes,

        # ==============================
        # COUNTERING
        # ==============================

        "date_countered": expense.date_countered,
        "counter_number": expense.counter_number,

        # ==============================
        # PAYMENT
        # ==============================

        "date_paid": expense.date_paid,
        "bank": expense.bank,
        "check_number": expense.check_number,

        "check_amount": decimal_to_float(
            expense.check_amount
        ),

        "receipt_number_2": expense.receipt_number_2,

        # ==============================
        # ACCOUNTS PAYABLE
        # ==============================

        "status": expense.status,

        "ap": decimal_to_float(
            expense.ap
        ),

        "remarks": expense.remarks,

        # ==============================
        # AUDIT
        # ==============================

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
    date: Optional[str] = Form(None),

    po_number: Optional[str] = Form(None),
    supplier: Optional[str] = Form(None),
    invoice_number: Optional[str] = Form(None),
    items: Optional[str] = Form(None),

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

    expense_number = generate_expense_number(db)

    created_at = datetime.utcnow()

    posting_period = calculate_posting_period(
        created_at
    )

    expense_items = parse_expense_items(items)

    expense = FinanceExpense(
        expense_number=expense_number,

        encoded_date=created_at,
        created_at=created_at,

        posting_period=posting_period,

        date=parsed_date,

        po_number=po_number,

        supplier=supplier,

        receipt_number=invoice_number,

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

    # -----------------------------------------
    # CREATE EXPENSE ITEMS
    # -----------------------------------------

    for item in expense_items:
        particulars = item.get("particulars")

        if not particulars:
            continue

        qty = Decimal(str(item.get("qty") or 1))
        unit = item.get("unit")
        unit_price = item.get("unit_price")

        if unit_price is not None:
            unit_price = Decimal(str(unit_price))
            amount = qty * unit_price
        else:
            amount = None

        expense_item = FinanceExpenseItem(
            expense_id=expense.id,
            particulars=particulars,
            qty=qty,
            unit=unit,
            unit_price=unit_price,
            amount=amount,
        )

        db.add(expense_item)

    db.commit()

    return api_response(
        serialize_expense(expense)
    )


# =========================================================
# UPDATE EXPENSE
# =========================================================

@router.patch("/{expense_id}")
async def update_expense(
    expense_id: int,

    date: Optional[str] = Form(None),

    po_number: Optional[str] = Form(None),
    supplier: Optional[str] = Form(None),
    invoice_number: Optional[str] = Form(None),
    items: Optional[str] = Form(None),

    # Legacy item fields
    # Kept temporarily for backward compatibility.
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

    # Parse items only when the frontend
    # actually sends the items field.
    expense_items = (
        parse_expense_items(items)
        if items is not None
        else None
    )

    validate_unit(unit)
    validate_status(status)

    # -----------------------------------------
    # BASIC FIELDS
    # -----------------------------------------

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

    if invoice_number is not None:
        expense.receipt_number = invoice_number

    # -----------------------------------------
    # LEGACY ITEM FIELDS
    # -----------------------------------------

    # These remain temporarily for backward
    # compatibility with existing records.

    if qty is not None:
        expense.qty = qty

    if unit is not None:
        expense.unit = unit

    if particulars is not None:
        expense.particulars = particulars

    if unit_price is not None:
        expense.unit_price = unit_price

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
    # ACCOUNTS PAYABLE
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
    # EXPENSE ITEMS
    # -----------------------------------------

    if expense_items is not None:

        existing_items = {
            item.id: item
            for item in expense.items
        }

        incoming_item_ids = set()

        for item_data in expense_items:
            item_id = item_data.get("id")

            item_particulars = item_data.get(
                "particulars"
            )

            # Ignore incomplete rows.
            if not item_particulars:
                continue

            item_qty = Decimal(
                str(
                    item_data.get("qty")
                    or 1
                )
            )

            item_unit = item_data.get("unit")

            item_unit_price = item_data.get(
                "unit_price"
            )

            # -----------------------------------------
            # UPDATE EXISTING ITEM
            # -----------------------------------------

            if (
                item_id is not None
                and item_id in existing_items
            ):
                expense_item = existing_items[item_id]

                # Preserve existing price when the
                # frontend doesn't provide one.
                if item_unit_price is None:
                    item_unit_price = (
                        expense_item.unit_price
                    )
                else:
                    item_unit_price = Decimal(
                        str(item_unit_price)
                    )

                if item_unit_price is not None:
                    item_amount = (
                        item_qty * item_unit_price
                    )
                else:
                    item_amount = None

                expense_item.particulars = (
                    item_particulars
                )

                expense_item.qty = item_qty
                expense_item.unit = item_unit
                expense_item.unit_price = (
                    item_unit_price
                )
                expense_item.amount = (
                    item_amount
                )

                incoming_item_ids.add(item_id)

            # -----------------------------------------
            # CREATE NEW ITEM
            # -----------------------------------------

            else:
                if item_unit_price is not None:
                    item_unit_price = Decimal(
                        str(item_unit_price)
                    )

                    item_amount = (
                        item_qty * item_unit_price
                    )
                else:
                    item_amount = None

                expense_item = FinanceExpenseItem(
                    expense_id=expense.id,
                    particulars=item_particulars,
                    qty=item_qty,
                    unit=item_unit,
                    unit_price=item_unit_price,
                    amount=item_amount,
                )

                db.add(expense_item)

        # -----------------------------------------
        # DELETE REMOVED ITEMS
        # -----------------------------------------

        for (
            item_id,
            existing_item,
        ) in existing_items.items():

            if item_id not in incoming_item_ids:
                db.delete(existing_item)

    # -----------------------------------------
    # AUDIT
    # -----------------------------------------

    expense.updated_by_user_id = (
        current_user.id
    )

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