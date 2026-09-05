from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

def generate_payslip_pdf(payslip, company, employee):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        spaceAfter=12
    )
    
    elements = []
    
    # Company Name
    company_name = company.name if company else "Acme Corp"
    elements.append(Paragraph(company_name, title_style))
    elements.append(Paragraph("Salary Slip", styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    # Employee Info Table
    emp_info = [
        ["Employee Name:", employee.name, "Month/Year:", f"{payslip.month}/{payslip.year}"],
        ["Designation:", employee.designation or "-", "Department:", employee.department or "-"],
        ["Days Worked:", f"{payslip.days_worked}/{payslip.payable_days}", "Generated On:", str(payslip.generated_on)]
    ]
    t1 = Table(emp_info, colWidths=[100, 130, 100, 130])
    t1.setStyle(TableStyle([
        ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(t1)
    elements.append(Spacer(1, 24))
    
    # Earnings & Deductions
    currency = company.currency_symbol if company else "$"
    data = [
        ['Earnings', 'Amount', 'Deductions', 'Amount'],
        ['Basic Salary', f"{currency}{payslip.basic:.2f}", 'PF', f"{currency}{payslip.pf:.2f}"],
        ['HRA', f"{currency}{payslip.hra:.2f}", 'Tax', f"{currency}{payslip.tax:.2f}"],
        ['Allowances', f"{currency}{payslip.allowances:.2f}", 'Other', f"{currency}{payslip.other_deductions:.2f}"],
        ['Bonus', f"{currency}{payslip.bonus:.2f}", '', '']
    ]
    
    total_earnings = payslip.basic + payslip.hra + payslip.allowances + payslip.bonus
    total_deductions = payslip.pf + payslip.tax + payslip.other_deductions
    
    data.append(['Total Earnings', f"{currency}{total_earnings:.2f}", 'Total Deductions', f"{currency}{total_deductions:.2f}"])
    
    t2 = Table(data, colWidths=[130, 100, 130, 100])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 24))
    
    # Net Salary
    elements.append(Paragraph(f"Net Salary: {currency}{payslip.net_salary:.2f}", styles['Heading2']))
    
    doc.build(elements)
    
    buffer.seek(0)
    return buffer
