from pydantic import BaseModel
from typing import Optional, List
import datetime


class DocumentTypeBase(BaseModel):
    title: str
    code: Optional[str] = None
    description: Optional[str] = None
    category: str = "KYC"
    is_mandatory: bool = False
    who_uploads: str = "employee"
    allowed_extensions: str = "pdf,jpg,jpeg,png,webp,docx"
    max_file_size_mb: int = 10
    department_id: Optional[int] = None
    is_active: bool = True
    display_order: int = 0


class DocumentTypeCreate(DocumentTypeBase):
    pass


class DocumentTypeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_mandatory: Optional[bool] = None
    who_uploads: Optional[str] = None
    allowed_extensions: Optional[str] = None
    max_file_size_mb: Optional[int] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class DocumentTypeOut(DocumentTypeBase):
    id: int
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class EmployeeDocumentOut(BaseModel):
    id: int
    employee_id: int
    document_type_id: Optional[int] = None
    custom_title: Optional[str] = None
    title: str
    file_name: str
    file_url: str
    file_size: int
    file_size_formatted: str
    file_extension: str
    mime_type: str
    status: str
    rejection_reason: Optional[str] = None
    verified_by_id: Optional[int] = None
    verified_at: Optional[datetime.datetime] = None
    uploaded_at: datetime.datetime

    class Config:
        from_attributes = True


class DocumentVerificationPayload(BaseModel):
    status: str  # "verified" or "rejected"
    rejection_reason: Optional[str] = None


class DocumentComplianceSummaryOut(BaseModel):
    total_employees: int
    fully_compliant_employees: int
    compliance_rate: float
    total_documents_uploaded: int
    pending_verifications: int
    rejected_documents: int
