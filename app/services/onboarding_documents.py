"""Documents an applicant can upload on the onboarding form -- the same
document types as Employee 201 -> Employment Files, so they carry over to
the employee on conversion (app/api/admin/applicants.py).

Stored in tpc_files as entity_type="applicant", entity_id=applicant.id
(next to the application's CV / SELFIE_PHOTO). All optional.
"""

APPLICANT_FILE_ENTITY = "applicant"

# key -> (label, drivers only)
ONBOARDING_DOCUMENTS = {
    "PROFILE_IMAGE": ("Profile Photo (2x2 / ID picture)", False),
    "NBI_CLEARANCE": ("NBI Clearance", False),
    "BRGY_CLEARANCE": ("Barangay Clearance", False),
    "POLICE_CLEARANCE": ("Police Clearance", True),
    "LICENSE": ("Driver's License (Front)", True),
    "LICENSE_BACK": ("Driver's License (Back)", True),
    "HEALTHCARD": ("Health Card", False),
    "XRAY": ("X-Ray", False),
    "NC3": ("NC3", False),
    "SSS": ("SSS ID / E-1 Form", False),
    "PHILHEALTH": ("PhilHealth ID / MDR", False),
    "PAGIBIG": ("Pag-IBIG ID / MDF", False),
    "ACCOUNT_NUMBER": ("ATM / Passbook / Bank App Screenshot", False),
}

# Also copied to the employee on conversion (from the application form).
CARRY_OVER_EXTRA = {"CV"}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def document_type_options():
    return [
        {"key": key, "label": label, "drivers_only": drivers_only}
        for key, (label, drivers_only) in ONBOARDING_DOCUMENTS.items()
    ]
