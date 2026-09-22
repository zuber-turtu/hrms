from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from io import BytesIO
from typing import Optional, List
import datetime
import os
import re

from app.database import get_db
from app.models.employee import Employee
from app.models.department import Department
from app.models.document import DocumentType, EmployeeDocument
from app.models.audit import AuditLog
from app.dependencies import require_auth, RoleChecker
from app.services.storage import get_storage_provider
from app.utils.timezone import get_ist_now

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

allow_hr_admin = RoleChecker(["admin", "hr_admin"])
allow_manager_or_hr = RoleChecker(["admin", "hr_admin", "manager"])


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")


# =========================================================================
# 1. ADMIN DYNAMIC DOCUMENT TYPES MANAGEMENT
# =========================================================================

@router.get("/documents/types", response_class=HTMLResponse)
async def list_document_types(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Admin page to configure dynamic document requirements and custom fields."""
    types = db.query(DocumentType).order_by(DocumentType.display_order.asc(), DocumentType.id.asc()).all()
    departments = db.query(Department).order_by(Department.name.asc()).all()
    
    # Calculate stats per document type
    stats = {}
    for dt in types:
        total_uploaded = db.query(EmployeeDocument).filter(EmployeeDocument.document_type_id == dt.id).count()
        verified_count = db.query(EmployeeDocument).filter(
            EmployeeDocument.document_type_id == dt.id,
            EmployeeDocument.status == "verified"
        ).count()
        stats[dt.id] = {
            "uploaded": total_uploaded,
            "verified": verified_count,
        }

    return templates.TemplateResponse(
        request=request,
        name="documents/types.html",
        context={
            "user": current_user,
            "document_types": types,
            "departments": departments,
            "stats": stats,
        },
    )


@router.post("/documents/types/create")
async def create_document_type(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category: str = Form("KYC"),
    is_mandatory: Optional[str] = Form(None),
    who_uploads: str = Form("employee"),
    allowed_extensions: str = Form("pdf,jpg,jpeg,png,webp"),
    max_file_size_mb: int = Form(10),
    department_id: Optional[str] = Form(None),
    display_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Creates a new dynamic document requirement field."""
    code = slugify(title)
    
    # Ensure unique code
    existing = db.query(DocumentType).filter(DocumentType.code == code).first()
    if existing:
        code = f"{code}_{os.urandom(2).hex()}"

    parsed_dept_id = int(department_id.strip()) if department_id and str(department_id).strip().isdigit() and int(department_id.strip()) > 0 else None

    doc_type = DocumentType(
        title=title.strip(),
        code=code,
        description=description.strip() if description else None,
        category=category.strip(),
        is_mandatory=bool(is_mandatory),
        who_uploads=who_uploads,
        allowed_extensions=allowed_extensions.strip().lower(),
        max_file_size_mb=max_file_size_mb,
        department_id=parsed_dept_id,
        display_order=display_order,
        is_active=True,
    )
    db.add(doc_type)
    db.commit()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="CREATE_DOCUMENT_TYPE",
        entity="DocumentType",
        entity_id=doc_type.id,
        new_value=f"Created custom document field: {doc_type.title} (Mandatory: {doc_type.is_mandatory})",
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/documents/types?success=Document+field+created+successfully", status_code=303)


@router.post("/documents/types/{type_id}/edit")
async def edit_document_type(
    type_id: int,
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category: str = Form("KYC"),
    is_mandatory: Optional[str] = Form(None),
    who_uploads: str = Form("employee"),
    allowed_extensions: str = Form("pdf,jpg,jpeg,png,webp"),
    max_file_size_mb: int = Form(10),
    department_id: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    display_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    doc_type = db.query(DocumentType).filter(DocumentType.id == type_id).first()
    if not doc_type:
        raise HTTPException(status_code=404, detail="Document field not found")

    parsed_dept_id = int(department_id.strip()) if department_id and str(department_id).strip().isdigit() and int(department_id.strip()) > 0 else None

    doc_type.title = title.strip()
    doc_type.description = description.strip() if description else None
    doc_type.category = category.strip()
    doc_type.is_mandatory = bool(is_mandatory)
    doc_type.who_uploads = who_uploads
    doc_type.allowed_extensions = allowed_extensions.strip().lower()
    doc_type.max_file_size_mb = max_file_size_mb
    doc_type.department_id = parsed_dept_id
    doc_type.is_active = bool(is_active)
    doc_type.display_order = display_order

    db.commit()
    return RedirectResponse(url="/documents/types?success=Document+field+updated+successfully", status_code=303)


@router.post("/documents/types/{type_id}/delete")
async def delete_document_type(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    doc_type = db.query(DocumentType).filter(DocumentType.id == type_id).first()
    if not doc_type:
        raise HTTPException(status_code=404, detail="Document field not found")

    db.delete(doc_type)
    db.commit()
    return RedirectResponse(url="/documents/types?success=Document+field+removed", status_code=303)


# =========================================================================
# 2. EMPLOYEE SELF-SERVICE VAULT & UPLOADS
# =========================================================================

def get_employee_document_checklist(employee: Employee, db: Session):
    """
    Computes all document requirements for an employee, matching uploaded documents
    against active DocumentTypes and verifying file availability in storage.
    """
    storage = get_storage_provider()

    # Active document types applicable to this employee's department or all
    query = db.query(DocumentType).filter(DocumentType.is_active.is_(True))
    if employee.department_id:
        query = query.filter(
            (DocumentType.department_id.is_(None)) | (DocumentType.department_id == employee.department_id)
        )
    else:
        query = query.filter(DocumentType.department_id.is_(None))

    all_types = query.order_by(DocumentType.display_order.asc(), DocumentType.id.asc()).all()

    # Existing uploaded documents for this employee
    uploaded_docs = db.query(EmployeeDocument).filter(EmployeeDocument.employee_id == employee.id).all()
    uploaded_map = {d.document_type_id: d for d in uploaded_docs if d.document_type_id}
    unmapped_docs = [d for d in uploaded_docs if not d.document_type_id]

    for d in unmapped_docs:
        d.is_file_available = storage.file_exists(d.file_url)

    checklist = []
    mandatory_total = 0
    mandatory_verified = 0

    for dt in all_types:
        existing = uploaded_map.get(dt.id)
        is_file_available = False
        if existing:
            is_file_available = storage.file_exists(existing.file_url)
            existing.is_file_available = is_file_available

        if dt.is_mandatory:
            mandatory_total += 1
            if existing and existing.status == "verified" and is_file_available:
                mandatory_verified += 1

        checklist.append({
            "type": dt,
            "document": existing,
            "is_uploaded": existing is not None,
            "is_file_available": is_file_available if existing else False,
            "status": existing.status if existing else "missing",
        })

    compliance_percent = int((mandatory_verified / mandatory_total * 100)) if mandatory_total > 0 else 100

    return {
        "checklist": checklist,
        "unmapped_docs": unmapped_docs,
        "mandatory_total": mandatory_total,
        "mandatory_verified": mandatory_verified,
        "compliance_percent": compliance_percent,
    }


@router.get("/my-documents", response_class=HTMLResponse)
async def my_documents_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Employee self-service document vault."""
    data = get_employee_document_checklist(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="documents/my_documents.html",
        context={
            "user": current_user,
            "employee": current_user,
            **data,
        },
    )


@router.post("/employees/{emp_id}/documents/upload")
async def upload_employee_document(
    emp_id: int,
    request: Request,
    file: UploadFile = File(...),
    document_type_id: Optional[str] = Form(None),
    custom_title: Optional[str] = Form(None),
    redirect_target: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Uploads a document for an employee with validation and storage persistence."""
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Authorization Check
    is_hr = current_user.role in ["admin", "hr_admin"]
    is_self = current_user.id == emp_id
    if not is_self and not is_hr:
        raise HTTPException(status_code=403, detail="Operation not permitted")

    parsed_doc_type_id = int(document_type_id.strip()) if document_type_id and str(document_type_id).strip().isdigit() and int(document_type_id.strip()) > 0 else None

    doc_type = None
    if parsed_doc_type_id:
        doc_type = db.query(DocumentType).filter(DocumentType.id == parsed_doc_type_id).first()
        if not doc_type:
            raise HTTPException(status_code=404, detail="Invalid Document Type")
        
        # Check who_uploads restriction
        if doc_type.who_uploads == "admin_only" and not is_hr:
            raise HTTPException(status_code=403, detail="This document can only be uploaded by HR Administration.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected for upload")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_size = len(file_bytes)
    max_size_mb = doc_type.max_file_size_mb if doc_type else 15
    if file_size > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of {max_size_mb} MB")

    # Validate allowed extensions
    ext = os.path.splitext(file.filename)[1].lower().strip(".")
    allowed_list = [x.strip() for x in (doc_type.allowed_extensions if doc_type else "pdf,jpg,jpeg,png,webp,docx").split(",")]
    if ext not in allowed_list:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '.{ext}'. Allowed formats: {', '.join(allowed_list)}"
        )

    # Upload to storage provider under 'documents/' folder
    storage = get_storage_provider()
    content_type = file.content_type or ("application/pdf" if ext == "pdf" else "image/jpeg")
    file_url, file_key = storage.upload_file(
        file_bytes,
        filename=file.filename,
        content_type=content_type,
        folder="documents",
    )

    # Check if this is a replacement of an existing document
    existing_doc = None
    if doc_type:
        existing_doc = db.query(EmployeeDocument).filter(
            EmployeeDocument.employee_id == employee.id,
            EmployeeDocument.document_type_id == doc_type.id
        ).first()

    if existing_doc:
        # Delete old file from storage if applicable
        try:
            storage.delete_file(existing_doc.file_url)
        except Exception:
            pass
        existing_doc.file_name = file.filename
        existing_doc.file_url = file_url
        existing_doc.file_size = file_size
        existing_doc.mime_type = content_type
        existing_doc.status = "verified" if is_hr else "pending"
        existing_doc.rejection_reason = None
        existing_doc.uploaded_at = get_ist_now()
        if is_hr:
            existing_doc.verified_by_id = current_user.id
            existing_doc.verified_at = get_ist_now()
        doc_record = existing_doc
    else:
        doc_record = EmployeeDocument(
            employee_id=employee.id,
            document_type_id=doc_type.id if doc_type else None,
            custom_title=custom_title.strip() if custom_title else None,
            file_name=file.filename,
            file_url=file_url,
            file_size=file_size,
            mime_type=content_type,
            status="verified" if is_hr else "pending",
            uploaded_at=get_ist_now(),
            verified_by_id=current_user.id if is_hr else None,
            verified_at=get_ist_now() if is_hr else None,
        )
        db.add(doc_record)

    db.commit()

    # Audit log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="UPLOAD_DOCUMENT",
        entity="EmployeeDocument",
        entity_id=doc_record.id,
        new_value=f"Uploaded {doc_record.title} for {employee.name} ({employee.email})",
    )
    db.add(audit)
    db.commit()

    if redirect_target:
        return RedirectResponse(url=f"{redirect_target}?success=Document+uploaded+successfully", status_code=303)
    
    if is_self and current_user.role not in ["admin", "hr_admin"]:
        return RedirectResponse(url="/my-documents?success=Document+uploaded+successfully", status_code=303)
    return RedirectResponse(url=f"/employees/{employee.id}#documents", status_code=303)


# =========================================================================
# 3. SECURE FILE VIEWING & DOWNLOADING (RBAC)
# =========================================================================

def check_document_access(document: EmployeeDocument, current_user: Employee):
    """Enforces strict RBAC: Owner, Manager of same dept, or HR Admin."""
    if current_user.role in ["admin", "hr_admin"]:
        return True
    if document.employee_id == current_user.id:
        return True
    if current_user.role == "manager":
        emp = document.employee
        if emp and emp.department_id == current_user.department_id and emp.role not in ["admin", "hr_admin"]:
            return True
    return False


@router.get("/documents/{doc_id}/view")
async def view_document_file(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Streams document binary for interactive in-browser preview."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user):
        raise HTTPException(status_code=403, detail="Access denied to this document.")

    storage = get_storage_provider()
    file_bytes = storage.get_file_bytes(document.file_url)
    
    if not file_bytes:
        # If stored as full external URL and provider doesn't support raw bytes, redirect
        if document.file_url.startswith("http://") or document.file_url.startswith("https://"):
            return RedirectResponse(url=document.file_url)
        raise HTTPException(status_code=404, detail="File could not be retrieved from storage.")

    media_type = document.mime_type or "application/pdf"
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.file_name}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/documents/{doc_id}/download")
async def download_document_file(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Forces file download with attachment header."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user):
        raise HTTPException(status_code=403, detail="Access denied to this document.")

    storage = get_storage_provider()
    
    # Check if signed download URL available
    signed_url = storage.get_signed_download_url(document.file_url)
    if signed_url:
        return RedirectResponse(url=signed_url)

    file_bytes = storage.get_file_bytes(document.file_url)
    if not file_bytes:
        if document.file_url.startswith("http://") or document.file_url.startswith("https://"):
            return RedirectResponse(url=document.file_url)
        raise HTTPException(status_code=404, detail="File could not be retrieved from storage.")

    return Response(
        content=file_bytes,
        media_type=document.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{document.file_name}"',
            "Cache-Control": "no-cache",
        },
    )


# =========================================================================
# 4. HR VERIFICATION & DELETION
# =========================================================================

@router.post("/documents/{doc_id}/verify")
async def verify_document(
    doc_id: int,
    status_choice: str = Form(...),  # "verified" or "rejected"
    rejection_reason: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """HR Admin document verification endpoint."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if status_choice not in ["verified", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="Invalid verification status")

    document.status = status_choice
    document.rejection_reason = rejection_reason.strip() if (status_choice == "rejected" and rejection_reason) else None
    document.verified_by_id = current_user.id
    document.verified_at = get_ist_now()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action=f"DOCUMENT_{status_choice.upper()}",
        entity="EmployeeDocument",
        entity_id=document.id,
        new_value=f"Marked document '{document.title}' for Employee #{document.employee_id} as {status_choice.upper()}" + (f": {rejection_reason}" if rejection_reason else ""),
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url=f"/employees/{document.employee_id}#documents", status_code=303)


@router.post("/documents/{doc_id}/delete")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Deletes an uploaded document."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    is_hr = current_user.role in ["admin", "hr_admin"]
    is_self = current_user.id == document.employee_id
    if not is_self and not is_hr:
        raise HTTPException(status_code=403, detail="Operation not permitted")

    emp_id = document.employee_id
    storage = get_storage_provider()
    try:
        storage.delete_file(document.file_url)
    except Exception:
        pass

    db.delete(document)
    db.commit()

    if is_self and current_user.role not in ["admin", "hr_admin"]:
        return RedirectResponse(url="/my-documents?success=Document+deleted", status_code=303)
    return RedirectResponse(url=f"/employees/{emp_id}#documents", status_code=303)


# =========================================================================
# 5. ORGANIZATION COMPLIANCE REPORT
# =========================================================================

@router.get("/documents/compliance", response_class=HTMLResponse)
async def documents_compliance_dashboard(
    request: Request,
    department_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_manager_or_hr),
):
    """Organization document compliance dashboard."""
    dept_id = None
    if department_id and str(department_id).strip().isdigit():
        dept_id = int(str(department_id).strip())

    query = db.query(Employee).filter(Employee.is_active.is_(True))
    if current_user.role == "manager":
        query = query.filter(Employee.department_id == current_user.department_id)
    elif dept_id:
        query = query.filter(Employee.department_id == dept_id)

    employees = query.order_by(Employee.name.asc()).all()
    departments = db.query(Department).order_by(Department.name.asc()).all()

    report_data = []
    total_compliant = 0
    total_pending_verifications = 0
    total_rejected = 0

    for emp in employees:
        checklist_data = get_employee_document_checklist(emp, db)
        is_compliant = checklist_data["compliance_percent"] == 100
        if is_compliant:
            total_compliant += 1

        pending_count = sum(1 for item in checklist_data["checklist"] if item["status"] == "pending")
        rejected_count = sum(1 for item in checklist_data["checklist"] if item["status"] == "rejected")
        total_pending_verifications += pending_count
        total_rejected += rejected_count

        if status_filter == "compliant" and not is_compliant:
            continue
        if status_filter == "pending" and pending_count == 0:
            continue
        if status_filter == "non_compliant" and is_compliant:
            continue

        report_data.append({
            "employee": emp,
            **checklist_data,
            "is_compliant": is_compliant,
            "pending_count": pending_count,
            "rejected_count": rejected_count,
        })

    overall_compliance_rate = round((total_compliant / len(employees) * 100), 1) if len(employees) > 0 else 100.0

    return templates.TemplateResponse(
        request=request,
        name="documents/compliance.html",
        context={
            "user": current_user,
            "report_data": report_data,
            "departments": departments,
            "selected_dept": dept_id,
            "selected_status": status_filter,
            "total_employees": len(employees),
            "total_compliant": total_compliant,
            "overall_compliance_rate": overall_compliance_rate,
            "total_pending_verifications": total_pending_verifications,
            "total_rejected": total_rejected,
        },
    )
