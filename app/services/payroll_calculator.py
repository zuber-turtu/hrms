from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.company import Company

def calculate_pro_rata(amount: float, days_worked: float, payable_days: int) -> float:
    if payable_days == 0:
        return 0.0
    return round(amount * (days_worked / payable_days), 2)

def generate_draft_payslip(db: Session, employee_id: int, month: int, year: int):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return None

    company = db.query(Company).first()
    working_days = company.working_days_per_month if company else 22
    payable_days = working_days # Simplified for this demo
    
    # Calculate days worked based on attendance
    attendances = db.query(Attendance).filter(
        Attendance.employee_id == employee_id,
        extract('month', Attendance.date) == month,
        extract('year', Attendance.date) == year
    ).all()
    
    # Simple calculation: count distinct days attended
    days_worked = float(len(set([a.date for a in attendances])))
    
    # Cap days worked at payable days
    days_worked = min(days_worked, payable_days)
    
    # Pro rata logic
    basic = calculate_pro_rata(employee.base_salary, days_worked, payable_days)
    hra = calculate_pro_rata(employee.hra, days_worked, payable_days)
    allowances = calculate_pro_rata(employee.custom_allowances, days_worked, payable_days)
    
    # Deductions are fixed or also pro-rated? Let's pro-rate deductions too
    pf = calculate_pro_rata(employee.pf_deduction, days_worked, payable_days)
    tax = calculate_pro_rata(employee.tax_deduction, days_worked, payable_days)
    
    net_salary = basic + hra + allowances - pf - tax
    
    return {
        "employee_id": employee.id,
        "month": month,
        "year": year,
        "payable_days": payable_days,
        "days_worked": days_worked,
        "basic": basic,
        "hra": hra,
        "allowances": allowances,
        "bonus": 0.0,
        "pf": pf,
        "tax": tax,
        "other_deductions": 0.0,
        "net_salary": net_salary
    }
