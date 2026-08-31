from sqlalchemy import Column, Integer, String
from app.database import Base

class Company(Base):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Acme Corp")
    address = Column(String, default="123 Enterprise Way")
    currency_symbol = Column(String, default="$")
    working_days_per_month = Column(Integer, default=22)
