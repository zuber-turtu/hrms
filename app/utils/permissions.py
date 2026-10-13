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
    "super_admin": {
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
    "admin": {
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
    "hr": {
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

ALL_CONFIGURABLE_ROLES = ["admin", "hr", "hr_admin", "manager", "employee", "intern"]

def get_company_permissions(company: Optional[Company]) -> Dict[str, Dict[str, bool]]:
    """
    Returns the parsed role permission matrix for the company, falling back to default standards.
    Super Admin is always fully enabled.
    """
    matrix = {r: {p["key"]: DEFAULT_ROLE_PERMISSIONS.get(r, {}).get(p["key"], False) for p in AVAILABLE_PERMISSIONS} for r in ALL_CONFIGURABLE_ROLES}
    matrix["super_admin"] = {p["key"]: True for p in AVAILABLE_PERMISSIONS}
    
    if company and company.role_permissions:
        try:
            stored = json.loads(company.role_permissions)
            if isinstance(stored, dict):
                for role, perms in stored.items():
                    if role in matrix and role != "super_admin" and isinstance(perms, dict):
                        for k, v in perms.items():
                            matrix[role][k] = bool(v)
        except Exception:
            pass

    return matrix


def has_role_permission(company: Optional[Company], role: str, perm_key: str) -> bool:
    """
    Checks if a role has the specified permission. Super Admin always has full access.
    """
    if role in ["super_admin", "admin"]:
        return True
    
    # Normalize hr alias
    lookup_role = "hr" if role == "hr_admin" else role
    matrix = get_company_permissions(company)
    return bool(matrix.get(lookup_role, {}).get(perm_key, False) or matrix.get(role, {}).get(perm_key, False))


# =========================================================================
# HIERARCHICAL ROLE-BASED ACCESS CONTROL (HRBAC) ENGINE
# Strict Hierarchy: Super Admin (100) > Admin (80) > HR Admin (60) > HR (50) > Manager (40) > Employee (20) > Intern (10)
# Rule: A lower role cannot modify, manage, promote, delete, or alter any higher or peer role.
# =========================================================================

ROLE_HIERARCHY: Dict[str, int] = {
    "super_admin": 100,
    "admin": 80,
    "hr_admin": 60,
    "hr": 50,
    "manager": 40,
    "employee": 20,
    "intern": 10,
}


def get_role_rank(role: Optional[str]) -> int:
    """Returns the numeric hierarchy rank of a given role string."""
    if not role:
        return 0
    return ROLE_HIERARCHY.get(str(role).strip().lower(), 0)


def can_manage_employee(actor: Optional[Any], target: Optional[Any]) -> bool:
    """
    Evaluates whether the actor has strictly higher hierarchical authority than the target employee.
    Rules:
    - Super Admin can manage anyone.
    - If actor or target is None, returns False.
    - If target is a super_admin, non-super_admins CANNOT manage them under any circumstances.
    - If actor.id == target.id, returns False (self-administration is handled separately to prevent self-role elevation).
    - Actor's rank MUST be strictly greater than target's rank: actor_rank > target_rank.
    """
    if not actor or not target:
        return False

    is_super = getattr(actor, "role", "") == "super_admin" or getattr(actor, "is_super_admin", False)
    if is_super:
        return True

    if getattr(target, "role", "") == "super_admin":
        return False

    actor_id = getattr(actor, "id", None)
    target_id = getattr(target, "id", None)
    if actor_id is not None and target_id is not None and actor_id == target_id:
        return False

    actor_rank = get_role_rank(getattr(actor, "role", None))
    target_rank = get_role_rank(getattr(target, "role", None))

    return actor_rank > target_rank


def can_assign_role(actor: Optional[Any], desired_role: Optional[str]) -> bool:
    """
    Validates whether the actor can grant/assign the desired role to another user.
    Rules:
    - Super Admin can assign any valid role.
    - An actor can ONLY assign roles strictly lower than their own rank.
      (e.g., Admin cannot assign Admin or Super Admin; HR cannot assign HR, Admin, or Super Admin).
    """
    if not actor or not desired_role:
        return False

    is_super = getattr(actor, "role", "") == "super_admin" or getattr(actor, "is_super_admin", False)
    if is_super:
        return True

    actor_rank = get_role_rank(getattr(actor, "role", None))
    desired_rank = get_role_rank(desired_role)

    return actor_rank > desired_rank


def assert_can_manage_employee(actor: Optional[Any], target: Optional[Any], action_name: str = "modify") -> None:
    """
    Raises HTTP 403 Forbidden if actor does not have hierarchical authority over target.
    """
    from fastapi import HTTPException, status

    if not actor or not target:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted: Cannot {action_name} target account."
        )

    is_super = getattr(actor, "role", "") == "super_admin" or getattr(actor, "is_super_admin", False)
    if is_super:
        return

    if getattr(target, "role", "") == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted: Cannot {action_name} a Super Admin account."
        )

    actor_rank = get_role_rank(getattr(actor, "role", None))
    target_rank = get_role_rank(getattr(target, "role", None))

    if actor_rank <= target_rank:
        actor_role_name = (getattr(actor, "role", "") or "User").replace("_", " ").title()
        target_role_name = (getattr(target, "role", "") or "Account").replace("_", " ").title()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted: A {actor_role_name} cannot {action_name} a {target_role_name} account."
        )


def assert_can_assign_role(actor: Optional[Any], desired_role: Optional[str]) -> None:
    """
    Raises HTTP 403 Forbidden if actor cannot assign desired_role.
    """
    from fastapi import HTTPException, status

    if not actor or not desired_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not permitted: Invalid role assignment."
        )

    is_super = getattr(actor, "role", "") == "super_admin" or getattr(actor, "is_super_admin", False)
    if is_super:
        return

    actor_rank = get_role_rank(getattr(actor, "role", None))
    desired_rank = get_role_rank(desired_role)

    if desired_rank >= actor_rank:
        actor_role_name = (getattr(actor, "role", "") or "User").replace("_", " ").title()
        desired_role_name = desired_role.replace("_", " ").title()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted: A {actor_role_name} cannot assign or promote an account to {desired_role_name}."
        )

