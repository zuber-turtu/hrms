from pydantic import BaseModel
from typing import Optional, List


class DesignationBase(BaseModel):
    title: str


class DesignationCreate(DesignationBase):
    department_id: Optional[int] = None


class DesignationOut(DesignationBase):
    id: int
    department_id: Optional[int] = None

    class Config:
        from_attributes = True


class DepartmentBase(BaseModel):
    name: str
    code: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentOut(DepartmentBase):
    id: int
    designations: List[DesignationOut] = []

    class Config:
        from_attributes = True
