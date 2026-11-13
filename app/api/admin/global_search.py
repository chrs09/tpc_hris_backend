# app/api/admin/global_search.py
#
# Superadmin's global search (the search box above the sidebar, Ctrl+K):
# one word or phrase matched anywhere (LIKE %term%) across the main
# records, grouped, each with a link to the page that lists it. The page
# opens filtered by the same term (?q=).

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, load_only

from app.core.database import get_db
from app.core.dependencies import require_superadmin

router = APIRouter(prefix="/global-search", tags=["Global Search"])

PER_GROUP = 8


def _like(term: str) -> str:
    # Typed % and _ are matched literally.
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _any(columns, like):
    return or_(*[c.ilike(like, escape="\\") for c in columns])


def _join(*parts) -> str:
    return " · ".join(str(p) for p in parts if p not in (None, ""))


@router.get("")
def global_search(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    from app.models.applicants import Applicant
    from app.models.customer import Customer
    from app.models.employees import Employee
    from app.models.finance_expense import FinanceExpense
    from app.models.stores import Store
    from app.models.supplier import Supplier
    from app.models.ticket import Ticket
    from app.models.trips import Trip
    from app.models.user import User
    from app.models.vehicle_unit import VehicleUnit
    from app.utils.timezone import utc_to_ph

    term = q.strip()
    if len(term) < 2:
        raise HTTPException(status_code=400, detail="Type at least 2 characters.")
    like = _like(term)
    qs = quote(term)
    groups = []

    def add(key, label, rows, item, path_all):
        items = [item(r) for r in rows[:PER_GROUP]]
        if items:
            groups.append({
                "key": key,
                "label": label,
                "items": items,
                "more": len(rows) > PER_GROUP,
                "path_all": path_all,
            })

    # People
    emps = (
        db.query(Employee)
        .filter(_any([Employee.first_name, Employee.last_name, Employee.middle_name,
                      Employee.email, Employee.position, Employee.department], like))
        .order_by(Employee.last_name)
        .limit(PER_GROUP + 1)
        .all()
    )
    add("employees", "Employees", emps, lambda e: {
        "title": " ".join(p for p in [e.first_name, e.last_name] if p),
        "subtitle": _join(e.position, e.department, "inactive" if not e.is_active else None),
        "path": f"/dashboard/employees?q={quote(e.last_name or term)}",
    }, f"/dashboard/employees?q={qs}")

    users = (
        db.query(User)
        .filter(_any([User.username, User.email], like))
        .order_by(User.username)
        .limit(PER_GROUP + 1)
        .all()
    )
    add("users", "Users", users, lambda u: {
        "title": u.username,
        "subtitle": _join(getattr(u.role, "value", u.role), u.email),
        "path": f"/dashboard/users?q={quote(u.username)}",
    }, f"/dashboard/users?q={qs}")

    apps = (
        db.query(Applicant)
        .filter(_any([Applicant.first_name, Applicant.last_name, Applicant.email,
                      Applicant.contact_number, Applicant.position_applied], like))
        .limit(PER_GROUP + 1)
        .all()
    )
    add("applicants", "Applicants", apps, lambda a: {
        "title": " ".join(p for p in [a.first_name, a.last_name] if p) or a.email,
        "subtitle": _join(a.position_applied, a.status),
        "path": f"/dashboard/applicants?q={quote(a.last_name or term)}",
    }, f"/dashboard/applicants?q={qs}")

    # Trips
    # ...or by the driver's name / username.
    driver_ids = (
        db.query(User.id)
        .outerjoin(Employee, Employee.id == User.employee_id)
        .filter(_any([User.username, Employee.first_name, Employee.last_name], like))
    )
    trips = (
        db.query(Trip)
        .filter(or_(
            _any([Trip.ticket_no, Trip.shipment_numbers, Trip.trip_code], like),
            Trip.driver_id.in_(driver_ids),
        ))
        .order_by(Trip.id.desc())
        .limit(PER_GROUP + 1)
        .all()
    )
    add("trips", "Trips", trips, lambda t: {
        "title": t.ticket_no or t.trip_code or f"Trip #{t.id}",
        "subtitle": _join(
            t.trip_code,
            t.driver.username if t.driver else None,
            utc_to_ph(t.start_time or t.created_at).strftime("%b %d, %Y") if (t.start_time or t.created_at) else None,
            getattr(t.status, "value", t.status),
        ),
        "path": f"/dashboard/office/trips?view=all&q={quote(t.trip_code or t.ticket_no or term)}",
    }, f"/dashboard/office/trips?view=all&q={qs}")

    # Locations, customers, suppliers
    stores = (
        db.query(Store)
        .filter(_any([Store.name, Store.address, Store.area, Store.outlet_number], like))
        .order_by(Store.name)
        .limit(PER_GROUP + 1)
        .all()
    )
    add("locations", "Locations", stores, lambda s: {
        "title": s.name,
        "subtitle": _join("Hub" if s.is_hub else None, "Supplier" if s.is_supplier else None,
                          s.area, s.address),
        "path": f"/dashboard/admin/stores?q={quote(s.name)}",
    }, f"/dashboard/admin/stores?q={qs}")

    customers = (
        db.query(Customer)
        .filter(_any([Customer.name, Customer.code, Customer.contact_person,
                      Customer.email, Customer.address], like))
        .order_by(Customer.name)
        .limit(PER_GROUP + 1)
        .all()
    )
    add("customers", "Customers", customers, lambda c: {
        "title": c.name,
        "subtitle": _join(c.code, c.contact_person, c.address),
        "path": "/dashboard/admin/customer-chart",
    }, "/dashboard/admin/customer-chart")

    suppliers = (
        db.query(Supplier)
        .filter(_any([Supplier.name, Supplier.contact_person, Supplier.email,
                      Supplier.phone, Supplier.address], like))
        .order_by(Supplier.name)
        .limit(PER_GROUP + 1)
        .all()
    )
    add("suppliers", "Suppliers", suppliers, lambda s: {
        "title": s.name,
        "subtitle": _join(s.contact_person, s.phone, s.address),
        "path": f"/dashboard/admin/suppliers?q={quote(s.name)}",
    }, f"/dashboard/admin/suppliers?q={qs}")

    # Fleet
    units = (
        db.query(VehicleUnit)
        .options(load_only(VehicleUnit.id, VehicleUnit.unit_code, VehicleUnit.plate_number,
                           VehicleUnit.description, VehicleUnit.is_active))
        .filter(_any([VehicleUnit.unit_code, VehicleUnit.plate_number,
                      VehicleUnit.description, VehicleUnit.cr_number, VehicleUnit.or_number], like))
        .limit(PER_GROUP + 1)
        .all()
    )
    add("vehicles", "Vehicles", units, lambda v: {
        "title": _join(v.unit_code, v.plate_number),
        "subtitle": _join(v.description, None if v.is_active else "inactive"),
        "path": f"/dashboard/admin/trip-maintenance?tab=units&q={quote(v.plate_number or v.unit_code or term)}",
    }, f"/dashboard/admin/trip-maintenance?tab=units&q={qs}")

    # Finance
    expenses = (
        db.query(FinanceExpense)
        .filter(_any([FinanceExpense.supplier, FinanceExpense.receipt_number,
                      FinanceExpense.po_number, FinanceExpense.expense_number], like))
        .order_by(FinanceExpense.id.desc())
        .limit(PER_GROUP + 1)
        .all()
    )
    add("expenses", "Expenses", expenses, lambda x: {
        "title": _join(x.supplier, x.receipt_number) or f"Expense #{x.id}",
        "subtitle": _join(x.expense_number, x.date.strftime("%b %d, %Y") if x.date else None,
                          f"PO {x.po_number}" if x.po_number else None),
        "path": f"/dashboard/finance/expenses?q={quote(x.receipt_number or x.supplier or term)}",
    }, f"/dashboard/finance/expenses?q={qs}")

    # Tickets
    tickets = (
        db.query(Ticket)
        .filter(_any([Ticket.ticket_no, Ticket.title, Ticket.description,
                      Ticket.requester_name, Ticket.requester_company], like))
        .order_by(Ticket.id.desc())
        .limit(PER_GROUP + 1)
        .all()
    )
    add("tickets", "Tickets", tickets, lambda t: {
        "title": t.title,
        "subtitle": _join(t.ticket_no, t.status, t.requester_name),
        "path": f"/dashboard/tickets?q={quote(t.ticket_no or t.title)}",
    }, f"/dashboard/tickets?q={qs}")

    return {"q": term, "groups": groups, "total": sum(len(g["items"]) for g in groups)}
