import json
from typing import Dict, Any, List, Optional
from app.models.company import Company

AVAILABLE_PERMISSIONS = [
    {
        "key": "employees_view",
        "category": "Workforce Directory",
        "name": "View Employee Directory",
        "description": "Access staff profiles, organizational structure, and department directories",
        "icon": "users",
    },
    {
        "key": "employees_manage",
        "category": "Workforce Directory",
        "name": "Staff Management",
        "description": "Add new employees, edit profiles, manage credentials, and terminate accounts",
        "icon": "user-cog",
    },
    {
        "key": "attendance_view",
        "category": "Time & Attendance",
        "name": "Attendance Oversight",
        "description": "Inspect team / organization daily punch logs, sessions, and geofence locations",
        "icon": "calendar-clock",
    },
    {
        "key": "attendance_override",
        "category": "Time & Attendance",
        "name": "Adjust & Override Punches",
        "description": "Manually adjust punch timestamps and regularize missed employee check-ins",
        "icon": "edit-3",
    },
    {
        "key": "leaves_approve",
        "category": "Leaves & Remote Work",
        "name": "Leave & WFH Approvals",
        "description": "Review and grant approvals for vacation, sick leaves, and Work From Home requests",
        "icon": "check-check",
    },
    {
        "key": "payroll_manage",
        "category": "Payroll & Compensation",
        "name": "Manage Payroll & Salary Slips",
        "description": "Calculate monthly pay, generate official payslips, and customize allowances/deductions",
        "icon": "wallet",
    },
    {
        "key": "documents_verify",
        "category": "Compliance & KYC",
        "name": "Review KYC & Documents",
        "description": "Inspect uploaded employee verification documents, approve or reject submissions",
        "icon": "file-check",
    },
    {
        "key": "company_settings",
        "category": "Administration & System",
        "name": "Organization Settings & Policies",
        "description": "Configure branding, work schedule standards, lunch break rules, and geofences",
        "icon": "settings",
    },
    {
        "key": "audit_logs",
        "category": "Administration & System",
        "name": "Security Audit Trail",
        "description": "Inspect security audit logs, employee status updates, and administrative modifications",
        "icon": "shield-alert",
    },
]

DEFAULT_ROLE_PERMISSIONS: Dict[str, Dict[str, bool]] = {
    "hr_admin": {
        "employees_view": True,
        "employees_manage": True,
        "attendance_view": True,
        "attendance_override": True,
        "leaves_approve": True,
        "payroll_manage": True,
        "documents_verify": True,
        "company_settings": True,
        "audit_logs": True,
    },
    "manager": {
        "employees_view": True,
        "employees_manage": False,
        "attendance_view": True,
        "attendance_override": True,
        "leaves_approve": True,
        "payroll_manage": False,
        "documents_verify": True,
        "company_settings": False,
        "audit_logs": False,
    },
    "employee": {
        "employees_view": True,
        "employees_manage": False,
        "attendance_view": False,
        "attendance_override": False,
        "leaves_approve": False,
        "payroll_manage": False,
        "documents_verify": False,
        "company_settings": False,
        "audit_logs": False,
    },
    "intern": {
        "employees_view": False,
        "employees_manage": False,
        "attendance_view": False,
        "attendance_override": False,
        "leaves_approve": False,
        "payroll_manage": False,
        "documents_verify": False,
        "company_settings": False,
        "audit_logs": False,
    },
}

def get_company_permissions(company: Optional[Company]) -> Dict[str, Dict[str, bool]]:
    """
    Returns the parsed role permission matrix for the company, falling back to default standards.
    """
    matrix = {r: {p["key"]: DEFAULT_ROLE_PERMISSIONS.get(r, {}).get(p["key"], False) for p in AVAILABLE_PERMISSIONS} for r in ["hr_admin", "manager", "employee", "intern"]}
    
    if company and company.role_permissions:
        try:
            stored = json.loads(company.role_permissions)
            if isinstance(stored, dict):
                for role, perms in stored.items():
                    if role in matrix and isinstance(perms, dict):
                        for k, v in perms.items():
                            matrix[role][k] = bool(v)
        except Exception:
            pass

    return matrix


def has_role_permission(company: Optional[Company], role: str, perm_key: str) -> bool:
    """
    Checks if a role has the specified permission. Admin always has full access.
    """
    if role == "admin":
        return True
    
    matrix = get_company_permissions(company)
    return bool(matrix.get(role, {}).get(perm_key, False))
