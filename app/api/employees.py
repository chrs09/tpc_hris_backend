import json
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from datetime import datetime
from typing import List
from fastapi.params import Query
from sqlalchemy import case
from sqlalchemy.orm import Session
from app.core.database import get_db

from app.utils.response import api_response

from app.models.employee_emergency import EmployeeEmergencyContact
from app.models.employee_family import EmployeeFamilyDetails
from app.models.employee_government import EmployeeGovernmentDetails
from app.models.employee_personal import EmployeePersonalDetails
from app.models.employee_education import EmployeeEducation
from app.models.employee_employment import EmployeeEmploymentHistory
from app.models.employee_reference import EmployeeReference
from app.models.employees import Employee
from app.models.user import User
from app.core.dependencies import get_current_user
from app.services.cv_parser import parse_cv
from app.models.files import File as FileModel
from app.services.file_service import FileService
from app.models.employee_inactive import EmployeeInactiveRecord

router = APIRouter(prefix="/employees", tags=["Employees"])


def parse_date(value: str):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def safe_json_loads(value: str, field_name: str):
    try:
        return json.loads(value or "[]")
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid JSON format for {field_name}"
        )


# ==============================
# Employee List (Only Active)
# ==============================
@router.get("/")
def get_employees(
    is_active: int = Query(
        1, description="Filter by active status: 1 for active, 0 for inactive"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department_order = case(
        (Employee.department == "Admin", 1),
        (Employee.department == "Yard", 2),
        (Employee.department == "Motorpool", 3),
        (Employee.department == "Dumptruck", 4),
        (Employee.department == "Labor", 5),
        (Employee.department == "CdcDriver", 6),
        (Employee.department == "CdcHelper", 7),
        (Employee.department == "CpdcDriver", 8),
        (Employee.department == "CpdcHelper", 9),
        else_=100,
    )

    employees = (
        db.query(Employee)
        .filter(Employee.is_active == is_active)
        .order_by(department_order, Employee.last_name.asc())
        .all()
    )

    employee_ids = [emp.id for emp in employees]

    files = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "employee",
            FileModel.entity_id.in_(employee_ids),
        )
        .all()
        if employee_ids
        else []
    )

    files_map = {}
    for file in files:
        files_map.setdefault(file.entity_id, []).append(
            {
                "document_type": file.document_type,
                "file_url": file.file_url,
            }
        )

    response = [
        {
            "id": emp.id,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "email": emp.email,
            "position": emp.position,
            "date_hired": str(emp.date_hired) if emp.date_hired else None,
            "department": emp.department,
            "is_active": emp.is_active,
            "is_available": emp.is_available,
            "created_by_user_id": emp.created_by_user_id,
            "files": files_map.get(emp.id, []),
        }
        for emp in employees
    ]

    return api_response(response)


# ==============================
# Employee Detail
# ==============================
@router.get("/{employee_id}")
def get_employee_detail(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    personal = (
        db.query(EmployeePersonalDetails).filter_by(employee_id=employee.id).first()
    )

    reference = db.query(EmployeeReference).filter_by(employee_id=employee.id).first()

    family = db.query(EmployeeFamilyDetails).filter_by(employee_id=employee.id).first()

    government = (
        db.query(EmployeeGovernmentDetails).filter_by(employee_id=employee.id).first()
    )

    emergency_contacts = (
        db.query(EmployeeEmergencyContact).filter_by(employee_id=employee.id).all()
    )

    education_records = (
        db.query(EmployeeEducation).filter_by(employee_id=employee.id).all()
    )

    employment_history = (
        db.query(EmployeeEmploymentHistory).filter_by(employee_id=employee.id).all()
    )

    files = (
        db.query(FileModel)
        .filter(
            FileModel.entity_type == "employee",
            FileModel.entity_id == employee.id,
        )
        .all()
    )
    latest_inactive_record = (
        db.query(EmployeeInactiveRecord)
        .filter(EmployeeInactiveRecord.employee_id == employee.id)
        .order_by(EmployeeInactiveRecord.created_at.desc())
        .first()
    )

    response = {
        "id": employee.id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "email": employee.email,
        "position": employee.position,
        "date_hired": employee.date_hired,
        "department": employee.department,
        "is_active": employee.is_active,
        "is_available": employee.is_available,
        "created_by_user_id": employee.created_by_user_id,
        "created_by_name": (
            employee.created_by_user.username if employee.created_by_user else None
        ),
        "updated_by_user_id": employee.updated_by_user_id,
        "updated_by_name": (
            employee.updated_by_user.username if employee.updated_by_user else None
        ),
        "updated_at": employee.updated_at,
        "personal_details": (
            {
                "employee_id": personal.employee_id,
                "birthday": personal.birthday,
                "birthplace": personal.birthplace if personal else None,
                "civil_status": personal.civil_status if personal else None,
                "gender": personal.gender if personal else None,
                "religion": personal.religion if personal else None,
                "citizenship": personal.citizenship if personal else None,
                "height": personal.height if personal else None,
                "weight": personal.weight if personal else None,
                "language": personal.language if personal else None,
                "contact_number": personal.contact_number if personal else None,
                "current_address": personal.current_address if personal else None,
                "provincial_address": personal.provincial_address if personal else None,
            }
            if personal
            else None
        ),
        "family_details": (
            {
                "employee_id": family.employee_id,
                "spouse_name": family.spouse_name,
                "father_name": family.father_name,
                "mother_name": family.mother_name,
            }
            if family
            else None
        ),
        "government_details": (
            {
                "employee_id": government.employee_id,
                "sss_number": government.sss_number,
                "philhealth_number": government.philhealth_number,
                "pagibig_number": government.pagibig_number,
                "tin_number": government.tin_number,
            }
            if government
            else None
        ),
        "character_reference": (
            {
                "employee_id": reference.employee_id,
                "name": reference.name,
                "occupation": reference.occupation,
                "contact": reference.contact,
                "address": reference.address,
            }
            if reference
            else None
        ),
        "emergency_contacts": [
            {
                "id": contact.id,
                "employee_id": contact.employee_id,
                "contact_name": contact.contact_name,
                "contact_number": contact.contact_number,
                "relationship_type": contact.relationship_type,
            }
            for contact in emergency_contacts
        ],
        "education_records": [
            {
                "id": edu.id,
                "level": edu.level,
                "institution": edu.institution,
                "degree": edu.degree,
                "year_from": edu.year_from,
                "year_to": edu.year_to,
                "skills": edu.skills,
            }
            for edu in education_records
        ],
        "employment_history": [
            {
                "id": job.id,
                "company_name": job.company_name,
                "position": job.position,
                "date_from": job.date_from,
                "date_to": job.date_to,
            }
            for job in employment_history
        ],
        "files": [
            {
                "document_type": f.document_type,
                "file_url": f.file_url,
            }
            for f in files
        ],
        "inactive_record": (
            {
                "id": latest_inactive_record.id,
                "inactive_reason": latest_inactive_record.inactive_reason,
                "inactive_date": latest_inactive_record.inactive_date,
                "inactive_remarks": latest_inactive_record.inactive_remarks,
                "created_at": latest_inactive_record.created_at,
                "created_by_user_id": latest_inactive_record.created_by_user_id,
                "reactivated_at": latest_inactive_record.reactivated_at,
                "reactivated_by_user_id": latest_inactive_record.reactivated_by_user_id,
            }
            if latest_inactive_record
            else None
        ),
    }

    return api_response(response)


# ==============================
# Employee Create (FULL RELATION)
# ==============================
@router.post("/", status_code=201)
async def create_employee(
    files: List[UploadFile] = File(None),
    document_types: List[str] = Form(None),
    # BASIC
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    position: str = Form(...),
    department: str = Form(...),
    date_hired: str = Form(...),
    # PERSONAL
    birthday: str = Form(None),
    birthplace: str = Form(None),
    civil_status: str = Form(None),
    gender: str = Form(None),
    # FAMILY
    spouse: str = Form(None),
    father_name: str = Form(None),
    mother_name: str = Form(None),
    # GOVERNMENT
    sss: str = Form(None),
    philhealth: str = Form(None),
    pagibig: str = Form(None),
    # EMERGENCY
    emergency_contact_name: str = Form(None),
    emergency_contact_number: str = Form(None),
    emergency_relationship: str = Form(None),
    # ARRAY FIELDS
    education_records: str = Form("[]"),
    employment_history: str = Form("[]"),
    # FILES
    # profile_image: UploadFile = File(None),
    # resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    parsed_education = safe_json_loads(education_records, "education_records")
    parsed_employment = safe_json_loads(employment_history, "employment_history")

    employee = Employee(
        first_name=first_name,
        last_name=last_name,
        email=email,
        position=position,
        department=department,
        date_hired=parse_date(date_hired),
        created_by_user_id=current_user.id,
        is_active=1,
    )

    db.add(employee)
    db.flush()

    # PERSONAL
    db.add(
        EmployeePersonalDetails(
            employee_id=employee.id,
            birthday=parse_date(birthday),
            birthplace=birthplace,
            civil_status=civil_status,
            gender=gender,
        )
    )

    # FAMILY
    db.add(
        EmployeeFamilyDetails(
            employee_id=employee.id,
            spouse_name=spouse,
            father_name=father_name,
            mother_name=mother_name,
        )
    )

    # GOVERNMENT
    db.add(
        EmployeeGovernmentDetails(
            employee_id=employee.id,
            sss_number=sss,
            philhealth_number=philhealth,
            pagibig_number=pagibig,
        )
    )

    # EMERGENCY
    if emergency_contact_name:
        db.add(
            EmployeeEmergencyContact(
                employee_id=employee.id,
                contact_name=emergency_contact_name,
                contact_number=emergency_contact_number,
                relationship_type=emergency_relationship,
            )
        )

    # EDUCATION
    for edu in parsed_education:
        if not any(
            [
                edu.get("level"),
                edu.get("institution"),
                edu.get("degree"),
                edu.get("year_from"),
                edu.get("year_to"),
                edu.get("skills"),
            ]
        ):
            continue

        db.add(
            EmployeeEducation(
                employee_id=employee.id,
                level=edu.get("level"),
                institution=edu.get("institution"),
                degree=edu.get("degree"),
                year_from=edu.get("year_from"),
                year_to=edu.get("year_to"),
                skills=edu.get("skills"),
            )
        )

    # EMPLOYMENT HISTORY
    for job in parsed_employment:
        if not any(
            [
                job.get("company_name"),
                job.get("position"),
                job.get("date_from"),
                job.get("date_to"),
            ]
        ):
            continue

        db.add(
            EmployeeEmploymentHistory(
                employee_id=employee.id,
                company_name=job.get("company_name"),
                position=job.get("position"),
                date_from=parse_date(job.get("date_from")),
                date_to=parse_date(job.get("date_to")),
            )
        )

    # FILES
    file_service = FileService()

    if files and document_types:

        if len(files) != len(document_types):
            raise HTTPException(
                status_code=400, detail="Files and document types mismatch"
            )

        for file, doc_type in zip(files, document_types):

            # upload file
            file_url = file_service.upload(file, f"employees/{employee.id}")

            # check existing (UPSERT)
            existing = (
                db.query(FileModel)
                .filter_by(
                    entity_type="employee",
                    entity_id=employee.id,
                    document_type=doc_type,
                )
                .first()
            )

            if existing:
                existing.file_url = file_url
            else:
                db.add(
                    FileModel(
                        entity_type="employee",
                        entity_id=employee.id,
                        document_type=doc_type,
                        file_url=file_url,
                        uploaded_by=current_user.id,
                    )
                )

    db.commit()

    return api_response({"message": "Employee created successfully"})


# ==============================
# Employee Update (Keep Active)
# ==============================
@router.patch("/{employee_id}")
async def patch_employee(
    employee_id: int,
    files: List[UploadFile] = File(None),
    document_types: List[str] = Form(None),
    # BASIC
    first_name: str = Form(None),
    last_name: str = Form(None),
    email: str = Form(None),
    position: str = Form(None),
    department: str = Form(None),
    date_hired: str = Form(None),
    is_active: int = Form(None),
    # INACTIVE DETAILS
    inactive_reason: str = Form(None),
    inactive_date: str = Form(None),
    inactive_remarks: str = Form(None),
    # PERSONAL
    birthday: str = Form(None),
    birthplace: str = Form(None),
    civil_status: str = Form(None),
    gender: str = Form(None),
    religion: str = Form(None),
    citizenship: str = Form(None),
    height: str = Form(None),
    weight: str = Form(None),
    language: str = Form(None),
    contact_number: str = Form(None),
    current_address: str = Form(None),
    provincial_address: str = Form(None),
    # FAMILY
    spouse: str = Form(None),
    father_name: str = Form(None),
    mother_name: str = Form(None),
    # REFERENCES
    reference_name: str = Form(None),
    reference_contact: str = Form(None),
    reference_address: str = Form(None),
    reference_occupation: str = Form(None),
    # GOVERNMENT
    sss: str = Form(None),
    philhealth: str = Form(None),
    pagibig: str = Form(None),
    tin: str = Form(None),
    # EMERGENCY
    emergency_contact_name: str = Form(None),
    emergency_contact_number: str = Form(None),
    emergency_relationship: str = Form(None),
    # ARRAY FIELDS
    education_records: str = Form(None),
    employment_history: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    previous_is_active = employee.is_active

    # =========================
    # BASIC
    # =========================
    if first_name is not None:
        employee.first_name = first_name
    if last_name is not None:
        employee.last_name = last_name
    if email is not None:
        employee.email = email
    if position is not None:
        employee.position = position
    if department is not None:
        employee.department = department
    if date_hired:
        employee.date_hired = datetime.strptime(date_hired, "%Y-%m-%d").date()

    if is_active is not None:
        employee.is_active = is_active

    # =========================
    # INACTIVE / REACTIVATE LOGIC
    # =========================
    if is_active is not None:
        # active -> inactive
        if previous_is_active == 1 and is_active == 0:
            if not inactive_reason:
                raise HTTPException(
                    status_code=400,
                    detail="inactive_reason is required when setting employee inactive",
                )

            if not inactive_date:
                raise HTTPException(
                    status_code=400,
                    detail="inactive_date is required when setting employee inactive",
                )

            db.add(
                EmployeeInactiveRecord(
                    employee_id=employee.id,
                    inactive_reason=inactive_reason,
                    inactive_date=parse_date(inactive_date),
                    inactive_remarks=inactive_remarks,
                    created_by_user_id=current_user.id,
                )
            )

        # inactive -> active
        elif previous_is_active == 0 and is_active == 1:
            latest_inactive = (
                db.query(EmployeeInactiveRecord)
                .filter(
                    EmployeeInactiveRecord.employee_id == employee.id,
                    EmployeeInactiveRecord.reactivated_at.is_(None),
                )
                .order_by(EmployeeInactiveRecord.created_at.desc())
                .first()
            )

            if latest_inactive:
                latest_inactive.reactivated_at = datetime.utcnow()
                latest_inactive.reactivated_by_user_id = current_user.id

    # =========================
    # UPDATE LOG
    # =========================
    employee.updated_by_user_id = current_user.id
    employee.updated_at = datetime.utcnow()

    # =========================
    # PERSONAL (UPSERT)
    # =========================
    personal = (
        db.query(EmployeePersonalDetails).filter_by(employee_id=employee.id).first()
    )

    if not personal:
        personal = EmployeePersonalDetails(employee_id=employee.id)
        db.add(personal)

    if birthday:
        personal.birthday = datetime.strptime(birthday, "%Y-%m-%d").date()
    if birthplace is not None:
        personal.birthplace = birthplace
    if civil_status is not None:
        personal.civil_status = civil_status
    if gender is not None:
        personal.gender = gender
    if religion is not None:
        personal.religion = religion
    if citizenship is not None:
        personal.citizenship = citizenship
    if height is not None:
        personal.height = height
    if weight is not None:
        personal.weight = weight
    if language is not None:
        personal.language = language
    if contact_number is not None:
        personal.contact_number = contact_number
    if current_address is not None:
        personal.current_address = current_address
    if provincial_address is not None:
        personal.provincial_address = provincial_address

    # =========================
    # FAMILY
    # =========================
    family = db.query(EmployeeFamilyDetails).filter_by(employee_id=employee.id).first()

    if not family:
        family = EmployeeFamilyDetails(employee_id=employee.id)
        db.add(family)

    if spouse is not None:
        family.spouse_name = spouse
    if father_name is not None:
        family.father_name = father_name
    if mother_name is not None:
        family.mother_name = mother_name

    # =========================
    # REFERENCES
    # =========================
    reference = db.query(EmployeeReference).filter_by(employee_id=employee.id).first()

    if not reference:
        reference = EmployeeReference(employee_id=employee.id)
        db.add(reference)

    if reference_name is not None:
        reference.name = reference_name
    if reference_contact is not None:
        reference.contact = reference_contact
    if reference_address is not None:
        reference.address = reference_address
    if reference_occupation is not None:
        reference.occupation = reference_occupation

    # =========================
    # GOVERNMENT
    # =========================
    gov = db.query(EmployeeGovernmentDetails).filter_by(employee_id=employee.id).first()

    if not gov:
        gov = EmployeeGovernmentDetails(employee_id=employee.id)
        db.add(gov)

    if sss is not None:
        gov.sss_number = sss
    if philhealth is not None:
        gov.philhealth_number = philhealth
    if pagibig is not None:
        gov.pagibig_number = pagibig
    if tin is not None:
        gov.tin_number = tin

    # =========================
    # EMERGENCY (REPLACE)
    # =========================
    if emergency_contact_name is not None:
        db.query(EmployeeEmergencyContact).filter_by(employee_id=employee.id).delete()

        if emergency_contact_name != "":
            db.add(
                EmployeeEmergencyContact(
                    employee_id=employee.id,
                    contact_name=emergency_contact_name,
                    contact_number=emergency_contact_number,
                    relationship_type=emergency_relationship,
                )
            )

    # =========================
    # EDUCATION (REPLACE)
    # =========================
    if education_records is not None:
        parsed_education = safe_json_loads(education_records, "education_records")

        db.query(EmployeeEducation).filter_by(employee_id=employee.id).delete()

        for edu in parsed_education:
            if not any(
                [
                    edu.get("level"),
                    edu.get("institution"),
                    edu.get("degree"),
                    edu.get("year_from"),
                    edu.get("year_to"),
                    edu.get("skills"),
                ]
            ):
                continue

            db.add(
                EmployeeEducation(
                    employee_id=employee.id,
                    level=edu.get("level"),
                    institution=edu.get("institution"),
                    degree=edu.get("degree"),
                    year_from=edu.get("year_from"),
                    year_to=edu.get("year_to"),
                    skills=edu.get("skills"),
                )
            )

    # =========================
    # EMPLOYMENT HISTORY (REPLACE)
    # =========================
    if employment_history is not None:
        parsed_employment = safe_json_loads(employment_history, "employment_history")

        db.query(EmployeeEmploymentHistory).filter_by(employee_id=employee.id).delete()

        for job in parsed_employment:
            if not any(
                [
                    job.get("company_name"),
                    job.get("position"),
                    job.get("date_from"),
                    job.get("date_to"),
                ]
            ):
                continue

            db.add(
                EmployeeEmploymentHistory(
                    employee_id=employee.id,
                    company_name=job.get("company_name"),
                    position=job.get("position"),
                    date_from=parse_date(job.get("date_from")),
                    date_to=parse_date(job.get("date_to")),
                )
            )

    # =========================
    # FILE UPSERT
    # =========================
    file_service = FileService()

    ALLOWED_DOCUMENT_TYPES = {
        "PROFILE_IMAGE",
        "CV",
        "CONTRACT",
        "NBI_CLEARANCE",
        "BRGY_CLEARANCE",
        "COMPANY_ID",
        "ACCOUNT_NUMBER",
        "ACCOUNTABILITY",
        "ID_FILE",
        "HEALTHCARD",
        "XRAY",
        "NC3",
    }

    if files and document_types:
        if len(files) != len(document_types):
            raise HTTPException(
                status_code=400, detail="Files and document types mismatch"
            )

        for file, doc_type in zip(files, document_types):
            if doc_type not in ALLOWED_DOCUMENT_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported document type: {doc_type}",
                )

            file_url = file_service.upload(file, f"employees/{employee.id}")

            existing = (
                db.query(FileModel)
                .filter_by(
                    entity_type="employee",
                    entity_id=employee.id,
                    document_type=doc_type,
                )
                .first()
            )

            if existing:
                existing.file_url = file_url
            else:
                db.add(
                    FileModel(
                        entity_type="employee",
                        entity_id=employee.id,
                        document_type=doc_type,
                        file_url=file_url,
                        uploaded_by=current_user.id,
                    )
                )

    db.commit()

    return api_response({"message": "Employee updated successfully"})


# ==============================
# Employee Soft Delete
# ==============================
@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if employee.is_active == 0:
        raise HTTPException(status_code=400, detail="Already inactive")

    employee.is_active = 0
    db.commit()

    return api_response({"message": "Employee deactivated"})


# CV PARSER
@router.post("/parse-cv")
async def parse_cv_endpoint(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        return {"error": "Only PDF files supported for now"}

    parsed_data = parse_cv(file.file)

    return api_response(parsed_data)
