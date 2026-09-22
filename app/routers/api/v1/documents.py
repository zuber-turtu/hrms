from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import re

from app.database import get_db
from app.models.employee import Employee
from app.models.document import DocumentType, EmployeeDocument
from app.models.audit import AuditLog
from app.schemas.document import (
    DocumentTypeCreate,
    DocumentTypeUpdate,
    DocumentTypeOut,
    EmployeeDocumentOut,
    DocumentVerificationPayload,
    DocumentComplianceSummaryOut,
)
from app.dependencies import require_auth, RoleChecker
from app.services.storage import get_storage_provider
from app.utils.timezone import get_ist_now

router = APIRouter(prefix="/documents", tags=["Documents & KYC"])

allow_hr_admin = RoleChecker(["admin", "hr_admin"])
allow_manager_or_hr = RoleChecker(["admin", "hr_admin", "manager"])


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")


def check_document_access(document: EmployeeDocument, current_user: Employee):
    if current_user.role in ["admin", "hr_admin"]:
        return True
    if document.employee_id == current_user.id:
        return True
    if current_user.role == "manager":
        emp = document.employee
        if emp and emp.department_id == current_user.department_id and emp.role not in ["admin", "hr_admin"]:
            return True
    return False


# =========================================================================
# DOCUMENT TYPES (DYNAMIC FIELDS CONFIGURATION)
# =========================================================================

@router.get("/types", response_model=List[DocumentTypeOut])
async def api_list_document_types(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """List all configured document requirement fields."""
    return db.query(DocumentType).filter(DocumentType.is_active.is_(True)).order_by(DocumentType.display_order.asc()).all()


@router.post("/types", response_model=DocumentTypeOut, status_code=status.HTTP_201_CREATED)
async def api_create_document_type(
    payload: DocumentTypeCreate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Create a new custom document requirement field."""
    code = slugify(payload.code or payload.title)
    existing = db.query(DocumentType).filter(DocumentType.code == code).first()
    if existing:
        code = f"{code}_{os.urandom(2).hex()}"

    doc_type = DocumentType(
        title=payload.title,
        code=code,
        description=payload.description,
        category=payload.category,
        is_mandatory=payload.is_mandatory,
        who_uploads=payload.who_uploads,
        allowed_extensions=payload.allowed_extensions.lower(),
        max_file_size_mb=payload.max_file_size_mb,
        department_id=payload.department_id,
        is_active=payload.is_active,
        display_order=payload.display_order,
    )
    db.add(doc_type)
    db.commit()
    db.refresh(doc_type)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="API_CREATE_DOCUMENT_TYPE",
        entity="DocumentType",
        entity_id=doc_type.id,
        new_value=f"{doc_type.title} (Mandatory: {doc_type.is_mandatory})",
    )
    db.add(audit)
    db.commit()

    return doc_type


@router.put("/types/{type_id}", response_model=DocumentTypeOut)
async def api_update_document_type(
    type_id: int,
    payload: DocumentTypeUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Update an existing document requirement field."""
    doc_type = db.query(DocumentType).filter(DocumentType.id == type_id).first()
    if not doc_type:
        raise HTTPException(status_code=404, detail="Document type not found")

    update_data = payload.dict(exclude_unset=True)
    for k, v in update_data.items():
        setattr(doc_type, k, v)

    db.commit()
    db.refresh(doc_type)
    return doc_type


@router.delete("/types/{type_id}")
async def api_delete_document_type(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """Delete a document requirement field."""
    doc_type = db.query(DocumentType).filter(DocumentType.id == type_id).first()
    if not doc_type:
        raise HTTPException(status_code=404, detail="Document type not found")

    db.delete(doc_type)
    db.commit()
    return {"message": f"Document type '{doc_type.title}' deleted successfully."}


# =========================================================================
# EMPLOYEE DOCUMENTS CRUD & UPLOAD
# =========================================================================

@router.get("/employee/{emp_id}", response_model=List[EmployeeDocumentOut])
async def api_get_employee_documents(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Get all documents uploaded for an employee."""
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    is_hr = current_user.role in ["admin", "hr_admin"]
    is_self = current_user.id == emp_id
    is_manager = current_user.role == "manager" and employee.department_id == current_user.department_id

    if not is_self and not is_hr and not is_manager:
        raise HTTPException(status_code=403, detail="Access denied")

    docs = db.query(EmployeeDocument).filter(EmployeeDocument.employee_id == emp_id).all()
    return docs


@router.post("/employee/{emp_id}/upload", response_model=EmployeeDocumentOut, status_code=status.HTTP_201_CREATED)
async def api_upload_employee_document(
    emp_id: int,
    file: UploadFile = File(...),
    document_type_id: Optional[int] = Form(None),
    custom_title: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Upload a document for an employee (PDF, image, or document format)."""
    employee = db.query(Employee).filter(Employee.id == emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    is_hr = current_user.role in ["admin", "hr_admin"]
    is_self = current_user.id == emp_id
    if not is_self and not is_hr:
        raise HTTPException(status_code=403, detail="Operation not permitted")

    doc_type = None
    if document_type_id and document_type_id > 0:
        doc_type = db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
        if not doc_type:
            raise HTTPException(status_code=404, detail="Invalid Document Type")
        if doc_type.who_uploads == "admin_only" and not is_hr:
            raise HTTPException(status_code=403, detail="This document can only be uploaded by HR Administration.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file content")

    file_size = len(file_bytes)
    max_size_mb = doc_type.max_file_size_mb if doc_type else 15
    if file_size > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds maximum size of {max_size_mb} MB")

    ext = os.path.splitext(file.filename)[1].lower().strip(".")
    allowed = [x.strip() for x in (doc_type.allowed_extensions if doc_type else "pdf,jpg,jpeg,png,webp,docx").split(",")]
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid file extension '.{ext}'. Allowed: {', '.join(allowed)}")

    storage = get_storage_provider()
    content_type = file.content_type or ("application/pdf" if ext == "pdf" else "image/jpeg")
    file_url, file_key = storage.upload_file(
        file_bytes,
        filename=file.filename,
        content_type=content_type,
        folder="documents",
    )

    existing_doc = None
    if doc_type:
        existing_doc = db.query(EmployeeDocument).filter(
            EmployeeDocument.employee_id == employee.id,
            EmployeeDocument.document_type_id == doc_type.id
        ).first()

    if existing_doc:
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
    db.refresh(doc_record)

    audit = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="API_UPLOAD_DOCUMENT",
        entity="EmployeeDocument",
        entity_id=doc_record.id,
        new_value=f"{doc_record.title} for {employee.name}",
    )
    db.add(audit)
    db.commit()

    return doc_record


# =========================================================================
# DOCUMENT DETAILS, DOWNLOAD & VERIFY
# =========================================================================

@router.get("/{doc_id}", response_model=EmployeeDocumentOut)
async def api_get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Get metadata for a single document with access validation."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    return document


@router.get("/{doc_id}/download")
async def api_download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Download document with access validation."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user):
        raise HTTPException(status_code=403, detail="Access denied")

    storage = get_storage_provider()
    signed_url = storage.get_signed_download_url(document.file_url)
    if signed_url:
        return {"download_url": signed_url}

    file_bytes = storage.get_file_bytes(document.file_url)
    if not file_bytes:
        if document.file_url.startswith("http://") or document.file_url.startswith("https://"):
            return {"download_url": document.file_url}
        raise HTTPException(status_code=404, detail="File could not be read from storage")

    return Response(
        content=file_bytes,
        media_type=document.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.file_name}"'},
    )


@router.put("/{doc_id}/verify", response_model=EmployeeDocumentOut)
@router.post("/{doc_id}/verify", response_model=EmployeeDocumentOut)
async def api_verify_document(
    doc_id: int,
    payload: DocumentVerificationPayload,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_hr_admin),
):
    """HR verify or reject an employee document."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.status not in ["verified", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    document.status = payload.status
    document.rejection_reason = payload.rejection_reason if payload.status == "rejected" else None
    document.verified_by_id = current_user.id
    document.verified_at = get_ist_now()

    db.commit()
    db.refresh(document)
    return document


@router.delete("/{doc_id}")
async def api_delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_auth),
):
    """Delete an employee document."""
    document = db.query(EmployeeDocument).filter(EmployeeDocument.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    is_hr = current_user.role in ["admin", "hr_admin"]
    is_self = current_user.id == document.employee_id
    if not is_self and not is_hr:
        raise HTTPException(status_code=403, detail="Operation not permitted")

    storage = get_storage_provider()
    try:
        storage.delete_file(document.file_url)
    except Exception:
        pass

    db.delete(document)
    db.commit()
    return {"message": f"Document '{document.title}' deleted successfully."}


@router.get("/compliance-summary", response_model=DocumentComplianceSummaryOut)
async def api_compliance_summary(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(allow_manager_or_hr),
):
    """Summary of company-wide document compliance rate."""
    employees = db.query(Employee).filter(Employee.is_active.is_(True)).all()
    mandatory_types = db.query(DocumentType).filter(DocumentType.is_active.is_(True), DocumentType.is_mandatory.is_(True)).all()
    mand_count = len(mandatory_types)

    total_uploaded = db.query(EmployeeDocument).count()
    pending = db.query(EmployeeDocument).filter(EmployeeDocument.status == "pending").count()
    rejected = db.query(EmployeeDocument).filter(EmployeeDocument.status == "rejected").count()

    compliant_count = 0
    for emp in employees:
        emp_verified = db.query(EmployeeDocument).filter(
            EmployeeDocument.employee_id == emp.id,
            EmployeeDocument.status == "verified",
            EmployeeDocument.document_type_id.in_([t.id for t in mandatory_types])
        ).count()
        if emp_verified >= mand_count:
            compliant_count += 1

    rate = round((compliant_count / len(employees) * 100), 1) if employees else 100.0

    return {
        "total_employees": len(employees),
        "fully_compliant_employees": compliant_count,
        "compliance_rate": rate,
        "total_documents_uploaded": total_uploaded,
        "pending_verifications": pending,
        "rejected_documents": rejected,
    }
