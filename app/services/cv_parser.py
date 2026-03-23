import re
from typing import Dict
import pdfplumber

# =============================
# TEXT EXTRACTION
# =============================


def extract_text_from_pdf(file) -> str:
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# =============================
# HELPER FUNCTION
# =============================


def find_field(label: str, text: str) -> str:
    pattern = rf"{label}\s*[:\-]?\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


# =============================
# BASIC INFO PARSER
# =============================


def parse_basic_information(text: str) -> Dict:
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    phone_match = re.search(r"(09\d{9})", text)

    lines = text.split("\n")

    first_name = ""
    last_name = ""

    if lines:
        possible_name = lines[0].strip().split(" ")
        if len(possible_name) >= 2:
            first_name = possible_name[0]
            last_name = possible_name[-1]

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email_match.group(0) if email_match else "",
        "contact_number": phone_match.group(0) if phone_match else "",
    }


# =============================
# STRUCTURED FIELD PARSER
# =============================


def parse_structured_fields(text: str) -> Dict:
    return {
        # PERSONAL
        "birthday": find_field("Birthday", text),
        "birthplace": find_field("Birthplace", text),
        "civil_status": find_field("Civil Status", text),
        "religion": find_field("Religion", text),
        "gender": find_field("Gender", text),
        "citizenship": find_field("Citizenship", text),
        "height": find_field("Height", text),
        "weight": find_field("Weight", text),
        "current_address": find_field("Current Address", text),
        "provincial_address": find_field("Provincial Address", text),
        # GOVERNMENT
        "sss": find_field("SSS", text),
        "philhealth": find_field("PhilHealth", text),
        "pagibig": find_field("Pag-IBIG", text),
        # EDUCATION
        "elementary": find_field("Elementary", text),
        "highschool": find_field("High School", text),
        "college": find_field("College", text),
        "degree": find_field("Degree", text),
        # EMPLOYMENT
        "prev_company": find_field("Company", text),
        "prev_position": find_field("Position", text),
        # CHARACTER REFERENCE
        "ref_name": find_field("Name", text),
        "ref_contact": find_field("Contact Number", text),
    }


# =============================
# MAIN PARSER
# =============================


def parse_cv(file) -> Dict:
    text = extract_text_from_pdf(file)

    basic = parse_basic_information(text)
    structured = parse_structured_fields(text)

    return {
        "basic": basic,
        "structured": structured,
    }
