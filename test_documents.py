import os
import sys
import io

# Force UTF-8 for stdout on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from main import app
from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department
from app.models.document import DocumentType, EmployeeDocument
from app.dependencies import get_password_hash, create_access_token

client = TestClient(app)

def run_document_tests():
    print("=" * 70)
    print("STARTING DYNAMIC DOCUMENT & MULTI-CLOUD STORAGE INTEGRATION TEST SUITE")
    print("=" * 70)

    # ---------------------------------------------------------
    # Setup test users and departments
    # ---------------------------------------------------------
    db = next(get_db())
    try:
        dept1 = db.query(Department).filter(Department.code == "DOC_ENG").first()
        if not dept1:
            dept1 = Department(name="Doc Engineering", code="DOC_ENG")
            db.add(dept1)
            db.commit()
            db.refresh(dept1)

        dept2 = db.query(Department).filter(Department.code == "DOC_SALES").first()
        if not dept2:
            dept2 = Department(name="Doc Sales", code="DOC_SALES")
            db.add(dept2)
            db.commit()
            db.refresh(dept2)

        # 1. Admin User
        admin_user = db.query(Employee).filter(Employee.email == "admin@hrms.local").first()
        assert admin_user is not None, "Admin user must exist"

        # 2. Manager in Dept 1
        mgr_user = db.query(Employee).filter(Employee.email == "doc_mgr@test.local").first()
        if not mgr_user:
            mgr_user = Employee(
                name="Doc Manager",
                email="doc_mgr@test.local",
                hashed_password=get_password_hash("Password@123"),
                role="manager",
                department_id=dept1.id,
                is_active=True
            )
            db.add(mgr_user)
            db.commit()
            db.refresh(mgr_user)

        # 3. Manager in Dept 2 (Different Department)
        other_mgr = db.query(Employee).filter(Employee.email == "doc_other_mgr@test.local").first()
        if not other_mgr:
            other_mgr = Employee(
                name="Other Manager",
                email="doc_other_mgr@test.local",
                hashed_password=get_password_hash("Password@123"),
                role="manager",
                department_id=dept2.id,
                is_active=True
            )
            db.add(other_mgr)
            db.commit()
            db.refresh(other_mgr)

        # 4. Employee 1 in Dept 1 (Subordinate to mgr_user)
        emp1 = db.query(Employee).filter(Employee.email == "doc_emp1@test.local").first()
        if not emp1:
            emp1 = Employee(
                name="Doc Employee 1",
                email="doc_emp1@test.local",
                hashed_password=get_password_hash("Password@123"),
                role="employee",
                department_id=dept1.id,
                is_active=True
            )
            db.add(emp1)
            db.commit()
            db.refresh(emp1)

        # 5. Employee 2 in Dept 2 (Different department)
        emp2 = db.query(Employee).filter(Employee.email == "doc_emp2@test.local").first()
        if not emp2:
            emp2 = Employee(
                name="Doc Employee 2",
                email="doc_emp2@test.local",
                hashed_password=get_password_hash("Password@123"),
                role="employee",
                department_id=dept2.id,
                is_active=True
            )
            db.add(emp2)
            db.commit()
            db.refresh(emp2)

        admin_email = admin_user.email
        mgr_email = mgr_user.email
        other_mgr_email = other_mgr.email
        emp1_email = emp1.email
        emp2_email = emp2.email

        emp1_id = emp1.id
        emp2_id = emp2.id

    finally:
        db.close()

    # Create tokens for API calls
    admin_token = create_access_token(data={"sub": admin_email})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    mgr_token = create_access_token(data={"sub": mgr_email})
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

    other_mgr_token = create_access_token(data={"sub": other_mgr_email})
    other_mgr_headers = {"Authorization": f"Bearer {other_mgr_token}"}

    emp1_token = create_access_token(data={"sub": emp1_email})
    emp1_headers = {"Authorization": f"Bearer {emp1_token}"}

    emp2_token = create_access_token(data={"sub": emp2_email})
    emp2_headers = {"Authorization": f"Bearer {emp2_token}"}

    # ---------------------------------------------------------
    # TEST 1: Default Document Types seeded & List
    # ---------------------------------------------------------
    print("\n[TEST 1] Verifying Seeded Document Types...")
    types_res = client.get("/api/v1/documents/types", headers=admin_headers)
    assert types_res.status_code == 200, f"Failed: {types_res.text}"
    types_data = types_res.json()
    assert len(types_data) >= 6, f"Expected at least 6 default document types, got {len(types_data)}"
    seeded_codes = [t["code"] for t in types_data]
    print(f"[OK] Found {len(types_data)} document types: {seeded_codes[:4]}...")
    assert "aadhaar_card" in seeded_codes
    assert "pan_card" in seeded_codes

    # ---------------------------------------------------------
    # TEST 2: Dynamic Document Type Creation (Admin vs Non-Admin)
    # ---------------------------------------------------------
    print("\n[TEST 2] Testing Dynamic Document Field Creation...")
    custom_code = f"tax_12bb_{os.urandom(2).hex()}"
    custom_payload = {
        "title": "Form 12BB Investment Declaration",
        "code": custom_code,
        "description": "Annual proof of IT investment deductions (80C, 80D, HRA)",
        "category": "Compliance",
        "allowed_extensions": "pdf,jpg,png",
        "max_file_size_mb": 5,
        "is_mandatory": True,
        "who_uploads": "employee",
        "is_active": True
    }

    # Non-admin attempt -> Expect 403
    forbidden_res = client.post("/api/v1/documents/types", headers=emp1_headers, json=custom_payload)
    assert forbidden_res.status_code == 403, f"Expected 403 for employee, got {forbidden_res.status_code}"
    print("[OK] Employee correctly denied permission to create document types (403).")

    # Admin creates dynamic field
    create_type_res = client.post("/api/v1/documents/types", headers=admin_headers, json=custom_payload)
    assert create_type_res.status_code == 201, f"Failed to create doc type: {create_type_res.text}"
    new_doc_type = create_type_res.json()
    new_doc_type_id = new_doc_type["id"]
    print(f"[OK] Admin created new dynamic document type: ID={new_doc_type_id}, Code='{new_doc_type['code']}'")

    # ---------------------------------------------------------
    # TEST 3: Employee Upload via REST API v1
    # ---------------------------------------------------------
    print("\n[TEST 3] Testing Document Upload via API v1...")
    
    # Create simulated PDF
    dummy_pdf_content = b"%PDF-1.4 test employee document binary content for Aadhaar Card verification"
    pdf_file = io.BytesIO(dummy_pdf_content)
    
    upload_res = client.post(
        f"/api/v1/documents/employee/{emp1_id}/upload",
        headers=emp1_headers,
        data={
            "document_type_id": new_doc_type_id,
            "custom_title": "Form 12BB 2026 Submission"
        },
        files={
            "file": ("declaration_proof.pdf", pdf_file, "application/pdf")
        }
    )
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    uploaded_doc = upload_res.json()
    doc_id = uploaded_doc["id"]
    assert uploaded_doc["status"] == "pending"
    print(f"[OK] Employee 1 successfully uploaded document ID {doc_id} (Status: pending).")

    # Disallowed MIME/Extension rejection
    bad_file = io.BytesIO(b"executable dummy code")
    bad_upload_res = client.post(
        f"/api/v1/documents/employee/{emp1_id}/upload",
        headers=emp1_headers,
        data={
            "document_type_id": new_doc_type_id,
        },
        files={
            "file": ("malicious.exe", bad_file, "application/x-msdownload")
        }
    )
    assert bad_upload_res.status_code == 400, f"Expected 400 for bad extension, got {bad_upload_res.status_code}"
    print("[OK] Invalid file format / extension correctly rejected with 400 Bad Request.")

    # ---------------------------------------------------------
    # TEST 4: RBAC on Document Retrieval & Streaming
    # ---------------------------------------------------------
    print("\n[TEST 4] Testing RBAC on Document Viewing & Streaming...")

    # 4a. Owner (emp1) views own document -> 200 OK
    owner_view_res = client.get(f"/documents/{doc_id}/view", headers=emp1_headers, follow_redirects=False)
    assert owner_view_res.status_code == 200, f"Owner view failed: {owner_view_res.status_code}"
    assert owner_view_res.content == dummy_pdf_content
    print("[OK] Document Owner can view/stream document (200 OK).")

    # 4b. Other Employee (emp2 in Dept 2) tries to view web route -> 303 Redirect (Access Denied)
    unauthorized_web_res = client.get(f"/documents/{doc_id}/view", headers=emp2_headers, follow_redirects=False)
    assert unauthorized_web_res.status_code == 303, f"Expected 303 redirect for other employee, got {unauthorized_web_res.status_code}"
    assert "Access+Denied" in unauthorized_web_res.headers.get("location", "")
    print("[OK] Unrelated employee blocked on web stream (303 Redirect to Access Denied).")

    # 4c. Other Employee tries to view via REST API -> 403 Forbidden
    unauthorized_api_res = client.get(f"/api/v1/documents/{doc_id}", headers=emp2_headers)
    assert unauthorized_api_res.status_code == 403, f"Expected 403 API response for other employee, got {unauthorized_api_res.status_code}"
    print("[OK] Unrelated employee blocked on REST API endpoint (403 Forbidden).")

    # 4d. Direct Department Manager (mgr_user in Dept 1) views -> 200 OK
    mgr_view_res = client.get(f"/documents/{doc_id}/view", headers=mgr_headers, follow_redirects=False)
    assert mgr_view_res.status_code == 200, f"Dept Manager view failed: {mgr_view_res.status_code}"
    print("[OK] Department Manager can view subordinate's document (200 OK).")

    # 4e. Other Department Manager (other_mgr in Dept 2) tries to view -> 303 Redirect / 403 API
    other_mgr_api_res = client.get(f"/api/v1/documents/{doc_id}", headers=other_mgr_headers)
    assert other_mgr_api_res.status_code == 403, f"Expected 403 API response for other dept manager, got {other_mgr_api_res.status_code}"
    print("[OK] Manager from another department blocked on REST API (403 Forbidden).")

    # 4f. Admin views -> 200 OK
    admin_view_res = client.get(f"/documents/{doc_id}/view", headers=admin_headers, follow_redirects=False)
    assert admin_view_res.status_code == 200, f"Admin view failed: {admin_view_res.status_code}"
    print("[OK] HR Admin can view any document (200 OK).")

    # ---------------------------------------------------------
    # TEST 5: Document Verification (Approval & Rejection)
    # ---------------------------------------------------------
    print("\n[TEST 5] Testing Document Verification Workflow...")

    # Non-admin employee attempts to verify -> 403
    emp_verify_res = client.put(
        f"/api/v1/documents/{doc_id}/verify",
        headers=emp1_headers,
        json={"status": "verified"}
    )
    assert emp_verify_res.status_code == 403, f"Expected 403 for employee, got {emp_verify_res.status_code}"
    print("[OK] Non-admin cannot verify documents (403 Forbidden).")

    # Admin rejects document with notes
    reject_res = client.put(
        f"/api/v1/documents/{doc_id}/verify",
        headers=admin_headers,
        json={
            "status": "rejected",
            "rejection_reason": "Signature missing on Page 2. Please re-upload signed copy."
        }
    )
    assert reject_res.status_code == 200, f"Rejection failed: {reject_res.text}"
    rejected_data = reject_res.json()
    assert rejected_data["status"] == "rejected"
    assert "Signature missing" in rejected_data["rejection_reason"]
    print(f"[OK] HR Admin rejected document with feedback note: '{rejected_data['rejection_reason']}'.")

    # Employee re-uploads -> new submission
    re_upload_res = client.post(
        f"/api/v1/documents/employee/{emp1_id}/upload",
        headers=emp1_headers,
        data={"document_type_id": new_doc_type_id},
        files={"file": ("declaration_signed.pdf", io.BytesIO(b"%PDF-1.4 fixed signed pdf"), "application/pdf")}
    )
    assert re_upload_res.status_code == 201
    new_uploaded_doc = re_upload_res.json()
    assert new_uploaded_doc["status"] == "pending"
    print(f"[OK] Employee re-uploaded revised document ID {new_uploaded_doc['id']} (Status: pending).")

    # Admin approves verified document
    approve_res = client.put(
        f"/api/v1/documents/{new_uploaded_doc['id']}/verify",
        headers=admin_headers,
        json={"status": "verified"}
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "verified"
    print(f"[OK] HR Admin approved document ID {new_uploaded_doc['id']} (Status: verified).")

    # ---------------------------------------------------------
    # TEST 6: Web UI Endpoints & HTML Templates Rendering
    # ---------------------------------------------------------
    print("\n[TEST 6] Testing Web UI Endpoints Rendering...")

    # 6a. Admin Document Types Management Page
    types_page_res = client.get("/documents/types", headers=admin_headers)
    assert types_page_res.status_code == 200
    assert "Document Types" in types_page_res.text
    print("[OK] Admin Document Fields configuration page rendered (200 OK).")

    # 6b. Employee Vault Page
    vault_page_res = client.get("/my-documents", headers=emp1_headers)
    assert vault_page_res.status_code == 200
    assert "Document Vault" in vault_page_res.text
    print("[OK] Employee 'My Documents' vault page rendered (200 OK).")

    # 6c. Organization KYC Compliance Page
    compliance_page_res = client.get("/documents/compliance", headers=admin_headers)
    assert compliance_page_res.status_code == 200
    assert "Compliance" in compliance_page_res.text
    print("[OK] KYC Compliance audit report rendered (200 OK).")

    # 6d. Employee Profile KYC Tab
    emp_profile_res = client.get(f"/employees/{emp1_id}/view", headers=admin_headers)
    assert emp_profile_res.status_code == 200
    assert "Documents &amp; KYC" in emp_profile_res.text or "Documents & KYC" in emp_profile_res.text
    assert "docPreviewModal" in emp_profile_res.text
    print("[OK] Employee profile Documents & KYC tab rendered with preview modal (200 OK).")

    # ---------------------------------------------------------
    # TEST 7: Multi-Cloud Storage Migration Script
    # ---------------------------------------------------------
    print("\n[TEST 7] Testing Multi-Cloud Storage Migration...")
    from migrate_storage import migrate_storage
    migrate_storage(
        source_name="local",
        target_name="local"
    )
    print("[OK] Storage migration utility executed successfully.")

    print("\n" + "=" * 70)
    print("ALL DOCUMENT & MULTI-CLOUD STORAGE INTEGRATION TESTS PASSED (100%)!")
    print("=" * 70)

if __name__ == "__main__":
    run_document_tests()
