import os
import sys

# Force UTF-8 for stdout on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def run_tests():
    print("=" * 60)
    print("STARTING REST API V1 COMPREHENSIVE INTEGRATION SUITE")
    print("=" * 60)

    # 1. AUTH - Admin Login
    print("\n[1] Testing Auth: Login Admin...")
    login_res = client.post("/api/v1/auth/login", json={
        "email": "admin@hrms.local",
        "password": "Admin@123"
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    login_data = login_res.json()
    admin_token = login_data["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"[OK] Admin logged in successfully. User: {login_data['user']['email']}, Role: {login_data['user']['role']}")

    # Test /api/v1/auth/me
    me_res = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me_res.status_code == 200
    print(f"[OK] /auth/me returned: {me_res.json()['name']} ({me_res.json()['role']})")

    # 2. DEPARTMENTS & DESIGNATIONS
    print("\n[2] Testing Departments & Designations...")
    # List departments
    dept_list_res = client.get("/api/v1/departments/", headers=admin_headers)
    assert dept_list_res.status_code == 200
    print(f"[OK] Listed {len(dept_list_res.json())} existing departments")

    # Create new department
    dept_suffix = os.urandom(2).hex()
    dept_name = f"Mobile Dev {dept_suffix}"
    dept_code = f"M{dept_suffix[:3].upper()}"
    create_dept_res = client.post("/api/v1/departments/", headers=admin_headers, json={
        "name": dept_name,
        "code": dept_code
    })
    assert create_dept_res.status_code == 201, f"Create dept failed: {create_dept_res.text}"
    dept_id = create_dept_res.json()["id"]
    print(f"[OK] Created Department ID {dept_id}: {dept_name}")

    # Create designation in department
    desig_title = f"Senior Flutter Engineer {os.urandom(2).hex()}"
    create_desig_res = client.post(f"/api/v1/departments/{dept_id}/designations", headers=admin_headers, json={
        "title": desig_title
    })
    assert create_desig_res.status_code == 201, f"Create desig failed: {create_desig_res.text}"
    desig_id = create_desig_res.json()["id"]
    print(f"[OK] Created Designation ID {desig_id}: {desig_title}")

    # 3. EMPLOYEES CRUD
    print("\n[3] Testing Employees CRUD...")
    test_email = f"emp_{os.urandom(3).hex()}@test.local"
    create_emp_payload = {
        "name": "Jane Tester",
        "email": test_email,
        "password": "EmpPassword@123",
        "role": "employee",
        "department_id": dept_id,
        "designation_id": desig_id,
        "phone": "+91 9876543210",
        "gender": "Female",
        "base_salary": 60000.0,
        "hra": 20000.0,
        "custom_allowances": 10000.0,
        "pf_deduction": 1800.0,
        "tax_deduction": 2500.0,
        "account_number": "123456789012",
        "bank_name": "HDFC Bank",
        "ifsc_code": "HDFC0001234"
    }
    create_emp_res = client.post("/api/v1/employees/", headers=admin_headers, json=create_emp_payload)
    assert create_emp_res.status_code == 201, f"Create emp failed: {create_emp_res.text}"
    emp_data = create_emp_res.json()
    emp_id = emp_data["id"]
    print(f"[OK] Created Employee ID {emp_id}: {emp_data['name']} ({emp_data['email']})")
    assert emp_data["salary_structure"]["base_salary"] == 60000.0

    # Get employee by ID
    get_emp_res = client.get(f"/api/v1/employees/{emp_id}", headers=admin_headers)
    assert get_emp_res.status_code == 200
    print(f"[OK] Fetched Employee ID {emp_id}: Dept = {get_emp_res.json()['department_name']}")

    # Update employee
    update_emp_res = client.put(f"/api/v1/employees/{emp_id}", headers=admin_headers, json={
        "name": "Jane Tester Updated",
        "base_salary": 65000.0
    })
    assert update_emp_res.status_code == 200
    assert update_emp_res.json()["name"] == "Jane Tester Updated"
    assert update_emp_res.json()["salary_structure"]["base_salary"] == 65000.0
    print(f"[OK] Updated Employee ID {emp_id} successfully")

    # Upload Employee Avatar via API
    dummy_img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
    avatar_upload_res = client.post(
        f"/api/v1/employees/{emp_id}/avatar",
        headers=admin_headers,
        files={"photo": ("avatar_test.png", dummy_img_bytes, "image/png")}
    )
    assert avatar_upload_res.status_code == 200, f"Avatar upload failed: {avatar_upload_res.text}"
    avatar_data = avatar_upload_res.json()
    assert avatar_data["avatar_url"] is not None
    assert "/uploads/avatars/" in avatar_data["avatar_url"] or "google" in avatar_data["avatar_url"]
    print(f"[OK] Uploaded Employee Avatar via REST API: {avatar_data['avatar_url']}")

    # Verify Avatar URL in employee profile
    get_emp_after_avatar = client.get(f"/api/v1/employees/{emp_id}", headers=admin_headers)
    assert get_emp_after_avatar.status_code == 200
    assert get_emp_after_avatar.json()["avatar_url"] == avatar_data["avatar_url"]
    print(f"[OK] Verified avatar_url persisted in Employee GET response")

    # 4. ATTENDANCE WORKFLOW (Using new Employee's Bearer token)
    print("\n[4] Testing Attendance Workflow...")
    emp_login_res = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": "EmpPassword@123"
    })
    assert emp_login_res.status_code == 200
    emp_token = emp_login_res.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Initial status
    status_res = client.get("/api/v1/attendance/status", headers=emp_headers)
    assert status_res.status_code == 200
    print(f"[OK] Initial Attendance Status: is_checked_in = {status_res.json()['is_checked_in']}")

    # Check in
    checkin_res = client.post("/api/v1/attendance/check-in", headers=emp_headers, json={"notes": "Starting mobile app testing"})
    assert checkin_res.status_code == 200
    assert checkin_res.json()["is_checked_in"] is True
    print("[OK] Check-in succeeded. Status is now ACTIVE")

    # Check out
    checkout_res = client.post("/api/v1/attendance/check-out", headers=emp_headers, json={"notes": "Break"})
    assert checkout_res.status_code == 200
    assert checkout_res.json()["is_checked_in"] is False
    print("[OK] Check-out succeeded. Status is now INACTIVE")

    # Check logs
    logs_res = client.get("/api/v1/attendance/logs", headers=emp_headers)
    assert logs_res.status_code == 200
    logs_data = logs_res.json()
    assert len(logs_data) >= 1
    log_id = logs_data[0]["id"]
    print(f"[OK] Employee logs fetched: {len(logs_data)} entry found (Log ID: {log_id})")

    # Admin attendance override
    override_res = client.post(f"/api/v1/attendance/{log_id}/override", headers=admin_headers, json={
        "check_in": "09:00:00",
        "check_out": "17:30:00",
        "notes": "Admin corrected shift timing"
    })
    assert override_res.status_code == 200
    print(f"[OK] Admin successfully overrode attendance log {log_id}")

    # 5. PAYROLL GENERATION, VIEW, EDIT & PDF
    print("\n[5] Testing Payroll API...")
    # Generate draft payslip
    draft_res = client.post("/api/v1/payroll/generate-draft", headers=admin_headers, json={
        "employee_id": emp_id,
        "month": 9,
        "year": 2026
    })
    assert draft_res.status_code == 201, f"Generate draft failed: {draft_res.text}"
    payslip_data = draft_res.json()
    payslip_id = payslip_data["id"]
    print(f"[OK] Generated Draft Payslip ID {payslip_id} for Employee {emp_id}. Net Salary: {payslip_data['net_salary']}")

    # Payroll summary
    summary_res = client.get("/api/v1/payroll/summary?month=9&year=2026", headers=admin_headers)
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    print(f"[OK] Payroll Summary: {summary_data['total_records']} records, Total Net: {summary_data['total_net']}, Drafts: {summary_data['draft_count']}")

    # Employee views payslip
    emp_payslip_res = client.get(f"/api/v1/payroll/payslips/{payslip_id}", headers=emp_headers)
    assert emp_payslip_res.status_code == 200
    assert emp_payslip_res.json()["employee_id"] == emp_id
    print("[OK] Employee successfully fetched own payslip")

    # Update payslip (Admin)
    update_payslip_res = client.put(f"/api/v1/payroll/payslips/{payslip_id}", headers=admin_headers, json={
        "bonus": 5000.0,
        "status": "finalized"
    })
    assert update_payslip_res.status_code == 200
    updated_slip = update_payslip_res.json()
    assert updated_slip["bonus"] == 5000.0
    assert updated_slip["status"] == "finalized"
    print(f"[OK] Updated payslip {payslip_id} with bonus and finalized status. New Net: {updated_slip['net_salary']}")

    # Download PDF
    pdf_res = client.get(f"/api/v1/payroll/payslips/{payslip_id}/pdf", headers=emp_headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 1000  # Non-trivial PDF size
    print(f"[OK] Streamed Payslip PDF successfully ({len(pdf_res.content)} bytes, Content-Type: application/pdf)")

    # 6. COMPANY PROFILE
    print("\n[6] Testing Company Profile API...")
    comp_res = client.get("/api/v1/company/profile", headers=admin_headers)
    assert comp_res.status_code == 200
    print(f"[OK] Fetched Company Profile: {comp_res.json()['name']} ({comp_res.json()['currency_symbol']})")

    update_comp_res = client.put("/api/v1/company/profile", headers=admin_headers, json={
        "name": "TURTU Enterprise Systems",
        "currency_symbol": "₹"
    })
    assert update_comp_res.status_code == 200
    assert update_comp_res.json()["name"] == "TURTU Enterprise Systems"
    assert update_comp_res.json()["currency_symbol"] == "₹"
    print("[OK] Updated Company Profile successfully")

    # 7. AUDIT LOGS
    print("\n[7] Testing Audit Logs API...")
    audit_res = client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) > 0
    print(f"[OK] Fetched {len(logs)} audit logs. Latest action: {logs[0]['action']} by {logs[0]['actor_email']}")

    print("\n" + "=" * 60)
    print("ALL REST API V1 INTEGRATION TESTS PASSED 100% SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
