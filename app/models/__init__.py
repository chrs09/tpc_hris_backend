from .employees import Employee as Employee
from .attendance import AttendanceRecord as AttendanceRecord
from .reminders import Reminder as Reminder
from .user import User as User  # if exists
from .trips import Trip as Trip  # if exists
from .trip_stops import TripStop as TripStop  # if exists
from .trip_helper import TripHelper as TripHelper  # if exists
from .notification import Notification as Notification  # if exists
from .stores import Store as Store  # if exists
from .gps_log import GPSLog as GPSLog  # if existsists
from .files import File as File  # if exists

# Applicant related models
from .employee_personal import EmployeePersonalDetails as EmployeePersonalDetails
from .employee_family import EmployeeFamilyDetails as EmployeeFamilyDetails
from .employee_emergency import EmployeeEmergencyContact as EmployeeEmergencyContact
from .employee_education import EmployeeEducation as EmployeeEducation
from .employee_employment import EmployeeEmploymentHistory as EmployeeEmploymentHistory
from .employee_reference import EmployeeReference as EmployeeReference
from .employee_government import EmployeeGovernmentDetails as EmployeeGovernmentDetails
from .employee_document import EmployeeDocument as EmployeeDocument

# Applicant related models
from .applicants import Applicant as Applicant
from .applicant_remarks import ApplicantRemark as ApplicantRemark
from .applicant_education import ApplicantEducation as ApplicantEducation
from .applicant_employment_history import ApplicantEmploymentHistory as ApplicantEmploymentHistory
from .applicant_references import ApplicantReference as ApplicantReference
from .applicant_onboarding import ApplicantOnboarding as ApplicantOnboarding
from .applicant_questions import ApplicantQuestion as ApplicantQuestion
from .applicant_qresponse import ApplicantQResponse as ApplicantQResponse
