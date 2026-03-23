from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.employee_emergency import EmployeeEmergencyContact
from app.models.employee_family import EmployeeFamilyDetails
from app.models.employee_government import EmployeeGovernmentDetails
from app.models.employee_personal import EmployeePersonalDetails
from app.models.employees import Employee
from app.models.user import User
from app.core.dependencies import get_current_user
from app.services.cv_parser import parse_cv
from app.models.files import File as FileModel
from app.services.file_service import FileService

router = APIRouter(prefix="/employees", tags=["Employees"])


# ==============================
# Employee List (Only Active)
# ==============================
@router.get("/")
def get_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Employee).filter(Employee.is_active == 1).all()


# ==============================
# Employee Detail
# ==============================
@router.get("/{employee_id}")
def get_employee_detail(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # =========================
    # BASE EMPLOYEE
    # =========================
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # =========================
    # RELATED TABLES
    # =========================
    personal = (
        db.query(EmployeePersonalDetails).filter_by(employee_id=employee.id).first()
    )

    family = db.query(EmployeeFamilyDetails).filter_by(employee_id=employee.id).first()

    government = (
        db.query(EmployeeGovernmentDetails).filter_by(employee_id=employee.id).first()
    )

    emergency_contacts = (
        db.query(EmployeeEmergencyContact).filter_by(employee_id=employee.id).all()
    )

    # ✅ UNIFIED FILES (IMPORTANT)
    files = (
        db.query(FileModel)
        .filter(FileModel.entity_type == "employee", FileModel.entity_id == employee.id)
        .all()
    )

    # =========================
    # BUILD RESPONSE
    # =========================
    return {
        **employee.__dict__,
        "personal_details": personal.__dict__ if personal else None,
        "family_details": family.__dict__ if family else None,
        "government_details": government.__dict__ if government else None,
        "emergency_contacts": [contact.__dict__ for contact in emergency_contacts],
        "files": [
            {"document_type": f.document_type, "file_url": f.file_url} for f in files
        ],
    }


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
    # FILES
    profile_image: UploadFile = File(None),
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = Employee(
        first_name=first_name,
        last_name=last_name,
        email=email,
        position=position,
        department=department,
        date_hired=date_hired,
        created_by_user_id=current_user.id,
        is_active=1,
    )

    db.add(employee)
    db.flush()

    # PERSONAL
    db.add(
        EmployeePersonalDetails(
            employee_id=employee.id,
            birthday=birthday,
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

    return {"message": "Employee created successfully"}


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
    # GOVERNMENT
    sss: str = Form(None),
    philhealth: str = Form(None),
    pagibig: str = Form(None),
    tin: str = Form(None),
    # EMERGENCY
    emergency_contact_name: str = Form(None),
    emergency_contact_number: str = Form(None),
    emergency_relationship: str = Form(None),
    # FILE
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

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

        db.add(
            EmployeeEmergencyContact(
                employee_id=employee.id,
                contact_name=emergency_contact_name,
                contact_number=emergency_contact_number,
                relationship_type=emergency_relationship,
            )
        )

    # =========================
    # FILE (UPSERT via FileService)
    # =========================
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

    return {"message": "Employee updated successfully"}


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

    return {"message": "Employee deactivated"}


# CV PARSER
@router.post("/parse-cv")
async def parse_cv_endpoint(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        return {"error": "Only PDF files supported for now"}

    parsed_data = parse_cv(file.file)

    return parsed_data
