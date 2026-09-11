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
from .employee_bank import EmployeeBank as EmployeeBank

# Applicant related models
from .applicants import Applicant as Applicant
from .applicant_remarks import ApplicantRemark as ApplicantRemark
from .applicant_education import ApplicantEducation as ApplicantEducation
from .applicant_employment_history import (
    ApplicantEmploymentHistory as ApplicantEmploymentHistory,
)
from .applicant_references import ApplicantReference as ApplicantReference
from .applicant_onboarding import ApplicantOnboarding as ApplicantOnboarding
from .applicant_questions import ApplicantQuestion as ApplicantQuestion
from .applicant_qresponse import ApplicantQResponse as ApplicantQResponse
from .employee_inactive import EmployeeInactiveRecord as EmployeeInactiveRecord

from .overtime_approvals import OvertimeApproval as OvertimeApproval
from .overtime_approval_details import OvertimeApprovalDetail as OvertimeApprovalDetail
from .schedule_template import ScheduleTemplate as ScheduleTemplate

# Trip Module
from .TripRate import TripRateProfile as TripRateProfile
from .vehicle_unit import VehicleUnit as VehicleUnit

# Fleet Management
from .customer import Customer as Customer
from .supplier import Supplier as Supplier
from .vehicle_maintenance import VehicleMaintenance as VehicleMaintenance

# Administrator related models
from .holiday import Holiday as Holiday
from .dispatch import Dispatch as Dispatch
from .dispatch_item import DispatchItem as DispatchItem
from .dispatch_helpers import DispatchHelper as DispatchHelper

from .holiday import Holiday as Holiday
from .payroll_deductions import PayrollDeduction as PayrollDeduction
from .finance_expense import FinanceExpense as FinanceExpense
from .finance_expense_item import FinanceExpenseItem as FinanceExpenseItem
from .trip_finance_review import TripFinanceReview as TripFinanceReview
from .leave_request import LeaveRequest as LeaveRequest
from .app_setting import AppSetting as AppSetting
from .user_revision import UserRevision as UserRevision
from .overtime_approver import OvertimeApprover as OvertimeApprover
from .overtime_request import OvertimeRequest as OvertimeRequest
from .department_head import DepartmentHead as DepartmentHead
from .employee_module_access import EmployeeModuleAccess as EmployeeModuleAccess
from .cash_advance_deduction_option import (
    CashAdvanceDeductionOption as CashAdvanceDeductionOption,
)
from .cash_advance_terms import CashAdvanceTerms as CashAdvanceTerms
from .cash_advance_request import CashAdvanceRequest as CashAdvanceRequest
from .cash_advance_deduction_log import (
    CashAdvanceDeductionLog as CashAdvanceDeductionLog,
)
