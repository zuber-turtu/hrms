from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship as orm_relationship
from app.database import Base
from app.utils.timezone import get_ist_now


class DocumentType(Base):
    """
    Dynamic Document Type definition created and managed by Admins.
    Allows HRMS to request arbitrary required or optional documents (e.g. Aadhaar, Degree, NDA, Safety Cert).
    """
    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)                         # e.g. "Aadhaar Card"
    code = Column(String, unique=True, index=True, nullable=False) # e.g. "aadhaar_card"
    description = Column(Text, nullable=True)                      # e.g. "Upload clear front and back scan in single PDF"
    
    # Category: "KYC", "Education", "Experience", "Company Letters", "Compliance", "Other"
    category = Column(String, default="KYC", nullable=False)
    
    # Requirement rules
    is_mandatory = Column(Boolean, default=False)
    who_uploads = Column(String, default="employee")               # "employee" or "admin_only"
    allowed_extensions = Column(String, default="pdf,jpg,jpeg,png,webp,docx")
    max_file_size_mb = Column(Integer, default=10)
    
    # Scope: optionally limit this document requirement to a specific department (e.g. Drivers only)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_ist_now)

    # Relational mappings
    department = orm_relationship("Department", backref="required_document_types")
    documents = orm_relationship("EmployeeDocument", back_populates="document_type", cascade="all, delete-orphan")


class EmployeeDocument(Base):
    """
    Individual document uploaded for or by an employee, with full verification lifecycle.
    """
    __tablename__ = "employee_documents"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    document_type_id = Column(Integer, ForeignKey("document_types.id"), nullable=True)
    
    # Title override or custom title if document_type_id is null
    custom_title = Column(String, nullable=True)
    
    # File metadata
    file_name = Column(String, nullable=False)                     # Original filename (e.g. "aadhaar_card.pdf")
    file_url = Column(String, nullable=False)                      # Stored URL / Key
    file_size = Column(Integer, default=0)                         # Size in bytes
    mime_type = Column(String, default="application/pdf")
    
    # Verification Lifecycle: "pending", "verified", "rejected"
    status = Column(String, default="pending", index=True)
    rejection_reason = Column(Text, nullable=True)
    verified_by_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    uploaded_at = Column(DateTime, default=get_ist_now)

    # Relational mappings
    employee = orm_relationship("Employee", foreign_keys=[employee_id], backref="documents")
    document_type = orm_relationship("DocumentType", back_populates="documents")
    verified_by = orm_relationship("Employee", foreign_keys=[verified_by_id])

    @property
    def title(self) -> str:
        if self.document_type:
            return self.document_type.title
        return self.custom_title or self.file_name

    @property
    def is_verified(self) -> bool:
        return self.status == "verified"

    @property
    def is_rejected(self) -> bool:
        return self.status == "rejected"

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def file_extension(self) -> str:
        if "." in self.file_name:
            return self.file_name.rsplit(".", 1)[-1].lower()
        return "file"

    @property
    def file_size_formatted(self) -> str:
        if not self.file_size:
            return "0 KB"
        if self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.1f} MB"
