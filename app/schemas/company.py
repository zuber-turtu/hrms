from pydantic import BaseModel
from typing import Optional


class CompanyProfileBase(BaseModel):
    name: str = "Acme Corp"
    address: Optional[str] = "123 Enterprise Way"
    currency_symbol: str = "$"
    working_days_per_month: int = 22


class CompanyProfileUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    currency_symbol: Optional[str] = None
    working_days_per_month: Optional[int] = None


class CompanyProfileOut(CompanyProfileBase):
    id: int

    class Config:
        from_attributes = True
