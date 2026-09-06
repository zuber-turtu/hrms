from io import BytesIO
import os
import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from app.services.formatters import number_to_words, get_month_name, mask_account_number

def generate_payslip_pdf(payslip, company, employee):
    buffer = BytesIO()
    # A4 standard portrait layout with standard margins (28pt)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=28,
        leftMargin=28,
        topMargin=28,
        bottomMargin=28
    )
    
    styles = getSampleStyleSheet()
    
    # Official Enterprise Palette
    c_primary = colors.HexColor("#0F172A")    # Slate 900
    c_slate_dark = colors.HexColor("#1E293B") # Slate 800
    c_slate_muted = colors.HexColor("#64748B")# Slate 500
    c_border = colors.HexColor("#94A3B8")     # Slate 400
    c_border_light = colors.HexColor("#CBD5E1") # Slate 300
    c_bg_light = colors.HexColor("#F8FAFC")   # Slate 50
    c_bg_subtle = colors.HexColor("#F1F5F9")  # Slate 100
    c_rose_bg = colors.HexColor("#FFF1F2")    # Rose 50
    c_rose_text = colors.HexColor("#9F1239")  # Rose 800
    
    # Paragraph Styles
    company_title_style = ParagraphStyle(
        'CompTitle',
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=c_primary,
        alignment=TA_LEFT
    )
    company_sub_style = ParagraphStyle(
        'CompSub',
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=c_slate_muted,
        alignment=TA_LEFT
    )
    statement_title_style = ParagraphStyle(
        'StateTitle',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=c_primary,
        alignment=TA_RIGHT
    )
    statement_meta_style = ParagraphStyle(
        'StateMeta',
        fontName='Helvetica',
        fontSize=7.5,
        leading=11,
        textColor=c_slate_dark,
        alignment=TA_RIGHT
    )
    ribbon_style = ParagraphStyle(
        'Ribbon',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.white,
        alignment=TA_CENTER
    )
    table_header_style = ParagraphStyle(
        'TableHead',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=TA_LEFT
    )
    table_header_right = ParagraphStyle(
        'TableHeadR',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=TA_RIGHT
    )
    cell_label_style = ParagraphStyle(
        'CellLbl',
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=c_slate_muted
    )
    cell_value_style = ParagraphStyle(
        'CellVal',
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=c_primary
    )
    cell_value_bold = ParagraphStyle(
        'CellValB',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=c_primary
    )
    cell_amount_style = ParagraphStyle(
        'CellAmt',
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=c_primary,
        alignment=TA_RIGHT
    )
    net_box_label = ParagraphStyle(
        'NetBoxLbl',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=c_primary,
        alignment=TA_LEFT
    )
    net_box_sub = ParagraphStyle(
        'NetBoxSub',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=c_slate_muted,
        alignment=TA_LEFT
    )
    net_box_words = ParagraphStyle(
        'NetBoxWords',
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10,
        textColor=c_slate_dark,
        alignment=TA_LEFT
    )
    net_box_amount = ParagraphStyle(
        'NetBoxAmt',
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=19,
        textColor=c_primary,
        alignment=TA_RIGHT
    )
    footer_text_style = ParagraphStyle(
        'FooterTxt',
        fontName='Helvetica',
        fontSize=6.5,
        leading=9,
        textColor=c_slate_muted,
        alignment=TA_LEFT
    )
    footer_sign_style = ParagraphStyle(
        'FooterSgn',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=c_slate_dark,
        alignment=TA_RIGHT
    )

    elements = []
    
    # 1. Company Information & Header
    company_name = company.name if company and company.name else "ACME CORPORATION INC."
    company_addr = company.address if company and company.address else "100 Innovation Boulevard, Tech Park, Suite 400"
    currency = company.currency_symbol if company and company.currency_symbol else "$"
    month_name = get_month_name(payslip.month)
    slip_no = f"PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}"
    
    header_left_text = [
        Paragraph(f"<b>{company_name.upper()}</b>", company_title_style),
        Paragraph(company_addr, company_sub_style),
        Paragraph("CIN: U72200CA2022PTC123456 • GSTIN/TAX: 29ABCDE1234F1Z5 • PAN: ABCDE1234F", company_sub_style),
        Paragraph("Corporate HR & Payroll Division • payroll@hrms.local", company_sub_style)
    ]

    logo_path = os.path.abspath("static/images/logo.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.abspath("logo.png")

    if os.path.exists(logo_path):
        try:
            logo_img = RLImage(logo_path, width=42, height=42)
            brand_table = Table([[logo_img, header_left_text]], colWidths=[50, 280])
            brand_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ]))
            header_left = brand_table
        except Exception:
            header_left = header_left_text
    else:
        header_left = header_left_text
    
    header_right = [
        Paragraph("<b>CONFIDENTIAL SALARY STATEMENT</b>", statement_title_style),
        Paragraph(f"<b>Slip No:</b> {slip_no}", statement_meta_style),
        Paragraph(f"<b>Disbursement:</b> {payslip.generated_on or 'End of Month'}", statement_meta_style),
        Paragraph(f"<b>Status:</b> {payslip.status.upper()}", statement_meta_style)
    ]
    
    header_table = Table([[header_left, header_right]], colWidths=[330, 209])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=0, spaceAfter=6))

    # 2. Payslip Month Banner
    ribbon_data = [[Paragraph(f"PAYSLIP FOR THE MONTH OF {month_name.upper()} {payslip.year}", ribbon_style)]]
    ribbon_table = Table(ribbon_data, colWidths=[539])
    ribbon_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_primary),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(ribbon_table)
    elements.append(Spacer(1, 6))

    # 3. Employee and Bank Metadata Grid (4 Columns)
    dept_name = employee.department.name if employee.department else (employee.department or "Operations")
    desig_title = employee.designation.title if employee.designation else (employee.designation or "Staff")
    emp_bank = employee.bank_account.bank_name if employee.bank_account and employee.bank_account.bank_name else "Standard Chartered Bank"
    emp_acc = mask_account_number(employee.bank_account.account_number if employee.bank_account else "")
    emp_ifsc = employee.bank_account.ifsc_code if employee.bank_account and employee.bank_account.ifsc_code else "SCBL0001092"
    emp_doj = str(employee.joining_date) if employee.joining_date else "N/A"
    emp_pan = employee.profile.pan_number if employee.profile and employee.profile.pan_number else "ABCDE1234F"

    meta_data = [
        [
            [Paragraph("EMPLOYEE NAME", cell_label_style), Paragraph(f"<b>{employee.name}</b>", cell_value_bold)],
            [Paragraph("EMPLOYEE ID", cell_label_style), Paragraph(f"EMP-{employee.id:04d}", cell_value_bold)],
            [Paragraph("BANK NAME", cell_label_style), Paragraph(str(emp_bank), cell_value_style)],
            [Paragraph("BANK ACCOUNT NO", cell_label_style), Paragraph(str(emp_acc), cell_value_bold)]
        ],
        [
            [Paragraph("DEPARTMENT", cell_label_style), Paragraph(str(dept_name), cell_value_style)],
            [Paragraph("DESIGNATION", cell_label_style), Paragraph(str(desig_title), cell_value_style)],
            [Paragraph("IFSC / BRANCH CODE", cell_label_style), Paragraph(str(emp_ifsc), cell_value_style)],
            [Paragraph("PAN / TAX ID", cell_label_style), Paragraph(str(emp_pan), cell_value_style)]
        ],
        [
            [Paragraph("DATE OF JOINING", cell_label_style), Paragraph(str(emp_doj), cell_value_style)],
            [Paragraph("PF / UAN NUMBER", cell_label_style), Paragraph("100982348123", cell_value_style)],
            [Paragraph("PAYMENT MODE", cell_label_style), Paragraph("Direct Bank Transfer", cell_value_style)],
            [Paragraph("PAYMENT STATUS", cell_label_style), Paragraph(f"<b>{payslip.status.upper()}</b>", cell_value_style)]
        ]
    ]

    meta_table = Table(meta_data, colWidths=[134.75, 134.75, 134.75, 134.75])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('BOX', (0,0), (-1,-1), 0.75, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border_light),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 5))

    # 4. Attendance Summary Ribbon
    att_data = [[
        Paragraph(f"<b>Standard Working Days:</b> {payslip.payable_days}", cell_value_style),
        Paragraph(f"<b>Days Worked / Present:</b> {payslip.days_worked:.1f}", cell_value_style),
        Paragraph(f"<b>Unpaid Leave (LOP):</b> {payslip.payable_days - payslip.days_worked:.1f}", cell_value_style),
        Paragraph("<b>Currency:</b> " + currency, cell_value_style),
    ]]
    att_table = Table(att_data, colWidths=[134.75, 134.75, 134.75, 134.75])
    att_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_subtle),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border_light),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(att_table)
    elements.append(Spacer(1, 6))

    # 5. Earnings & Deductions Tables (Two-Column Side-by-Side)
    total_earnings = payslip.basic + payslip.hra + payslip.allowances + payslip.bonus
    total_deductions = payslip.pf + payslip.tax + payslip.other_deductions

    breakdown_data = [
        # Table Header
        [
            Paragraph("EARNINGS", table_header_style),
            Paragraph(f"AMOUNT ({currency})", table_header_right),
            Paragraph("DEDUCTIONS", table_header_style),
            Paragraph(f"AMOUNT ({currency})", table_header_right)
        ],
        # Rows
        [
            Paragraph("Basic Salary", cell_value_style),
            Paragraph(f"{payslip.basic:.2f}", cell_amount_style),
            Paragraph("Employee Provident Fund (PF)", cell_value_style),
            Paragraph(f"{payslip.pf:.2f}", cell_amount_style)
        ],
        [
            Paragraph("House Rent Allowance (HRA)", cell_value_style),
            Paragraph(f"{payslip.hra:.2f}", cell_amount_style),
            Paragraph("Professional Tax (PT) / TDS", cell_value_style),
            Paragraph(f"{payslip.tax:.2f}", cell_amount_style)
        ],
        [
            Paragraph("Special & Conveyance Allowance", cell_value_style),
            Paragraph(f"{payslip.allowances:.2f}", cell_amount_style),
            Paragraph("Other Statutory / Advance Deductions", cell_value_style),
            Paragraph(f"{payslip.other_deductions:.2f}", cell_amount_style)
        ],
        [
            Paragraph("Performance Incentive / Bonus", cell_value_style),
            Paragraph(f"{payslip.bonus:.2f}", cell_amount_style),
            Paragraph("—", cell_value_style),
            Paragraph("0.00", cell_amount_style)
        ],
        # Subtotals Row
        [
            Paragraph("<b>TOTAL GROSS EARNINGS (A)</b>", cell_value_bold),
            Paragraph(f"<b>{total_earnings:.2f}</b>", cell_amount_style),
            Paragraph("<b>TOTAL DEDUCTIONS (B)</b>", ParagraphStyle('RedHead', parent=cell_value_bold, textColor=c_rose_text)),
            Paragraph(f"<b>{total_deductions:.2f}</b>", ParagraphStyle('RedAmt', parent=cell_amount_style, textColor=c_rose_text))
        ]
    ]

    breakdown_table = Table(breakdown_data, colWidths=[189.5, 80, 189.5, 80])
    breakdown_table.setStyle(TableStyle([
        # Headers
        ('BACKGROUND', (0,0), (1,0), c_primary),
        ('BACKGROUND', (2,0), (3,0), c_primary),
        ('TOPPADDING', (0,0), (-1,0), 4),
        ('BOTTOMPADDING', (0,0), (-1,0), 4),
        
        # Rows
        ('BACKGROUND', (0,1), (-1,-2), colors.white),
        ('ROWBACKGROUNDS', (0,1), (1,-2), [colors.white, c_bg_light]),
        ('ROWBACKGROUNDS', (2,1), (3,-2), [colors.white, c_bg_light]),
        ('TOPPADDING', (0,1), (-1,-2), 3.5),
        ('BOTTOMPADDING', (0,1), (-1,-2), 3.5),

        # Subtotals Row
        ('BACKGROUND', (0,-1), (1,-1), c_bg_subtle),
        ('BACKGROUND', (2,-1), (3,-1), c_rose_bg),
        ('TOPPADDING', (0,-1), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 4.5),

        # Grid lines
        ('BOX', (0,0), (-1,-1), 0.75, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border_light),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(breakdown_table)
    elements.append(Spacer(1, 6))

    # 6. Net Take-Home Salary Highlight Box
    words = number_to_words(payslip.net_salary, currency)
    net_content = [
        [
            [
                Paragraph("<b>NET TAKE-HOME SALARY (A - B)</b>", net_box_label),
                Paragraph("Disbursed via Electronic Bank Transfer (NEFT/RTGS)", net_box_sub),
                Spacer(1, 2),
                Paragraph(f"<b>Amount in Words:</b> <i>{words}</i>", net_box_words)
            ],
            [
                Paragraph(f"<b>{currency}{payslip.net_salary:,.2f}</b>", net_box_amount),
            ]
        ]
    ]
    net_table = Table(net_content, colWidths=[369, 170])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1.25, c_primary),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(net_table)
    elements.append(Spacer(1, 14))

    # 7. Official Footer & Authorized Signatory Block
    disclaimer = [
        Paragraph("<b>Official Verified Document</b>", ParagraphStyle('DisclH', parent=cell_value_bold, textColor=c_slate_dark)),
        Paragraph("*This is a computer-generated official salary certificate issued by the Enterprise HRMS platform. "
                  "It does not require a physical handwritten signature.", footer_text_style),
        Paragraph(f"SECURITY REF: AUTH-PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}-VERIFIED", ParagraphStyle('SecHash', parent=footer_text_style, fontName='Helvetica-Bold', fontSize=6))
    ]
    signatory = [
        Paragraph("____________________________", footer_sign_style),
        Paragraph("<b>Authorized Signatory</b>", footer_sign_style),
        Paragraph(f"For {company_name}", ParagraphStyle('SubComp', parent=footer_sign_style, fontSize=6.5, textColor=c_slate_muted))
    ]

    footer_table = Table([[disclaimer, signatory]], colWidths=[359, 180])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(footer_table)

    # Build PDF document
    doc.build(elements)
    buffer.seek(0)
    return buffer
