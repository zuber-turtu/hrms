from io import BytesIO
import os
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.services.formatters import number_to_words, get_month_name, mask_account_number

# Font Registration Flag
_FONTS_REGISTERED = False

def register_brand_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    
    font_dir = os.path.abspath("static/fonts")
    
    # Register Nunito
    nunito_path = os.path.join(font_dir, "Nunito-Regular.ttf")
    if os.path.exists(nunito_path):
        try:
            pdfmetrics.registerFont(TTFont("Nunito", nunito_path))
            pdfmetrics.registerFont(TTFont("Nunito-Bold", nunito_path))
        except Exception:
            pass

    # Register Poppins
    poppins_bold_path = os.path.join(font_dir, "Poppins-Bold.ttf")
    if os.path.exists(poppins_bold_path):
        try:
            pdfmetrics.registerFont(TTFont("Poppins-Bold", poppins_bold_path))
        except Exception:
            pass

    poppins_semi_path = os.path.join(font_dir, "Poppins-SemiBold.ttf")
    if os.path.exists(poppins_semi_path):
        try:
            pdfmetrics.registerFont(TTFont("Poppins-SemiBold", poppins_semi_path))
        except Exception:
            pass

    # Register JetBrains Mono
    mono_path = os.path.join(font_dir, "JetBrainsMono-Regular.ttf")
    if os.path.exists(mono_path):
        try:
            pdfmetrics.registerFont(TTFont("JetBrainsMono", mono_path))
            pdfmetrics.registerFont(TTFont("JetBrainsMono-Bold", mono_path))
        except Exception:
            pass

    _FONTS_REGISTERED = True


def get_font_name(preferred: str, fallback: str = "Helvetica") -> str:
    """Returns the preferred font if registered in ReportLab, otherwise falls back gracefully."""
    registered = pdfmetrics.getRegisteredFontNames()
    if preferred in registered:
        return preferred
    return fallback


def generate_payslip_pdf(payslip, company, employee):
    register_brand_fonts()

    buffer = BytesIO()
    # A4 standard portrait layout with standard margins (26pt)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=26,
        leftMargin=26,
        topMargin=26,
        bottomMargin=26
    )
    
    # TURTU Brand Color Palette
    c_dark = colors.HexColor("#004444")        # Dark Forest (Headers, Ribbon)
    c_teal = colors.HexColor("#008080")        # Primary Teal (Accents, Totals, Borders)
    c_forest = colors.HexColor("#005050")      # Teal Forest
    c_mist = colors.HexColor("#E0F4F4")        # Teal Mist (Highlight fills, badges)
    c_light = colors.HexColor("#B3E3E3")       # Teal Light (Dividers, borders)
    c_wash = colors.HexColor("#F4F7F7")        # Teal Wash (Alternating rows, container fills)
    c_text_primary = colors.HexColor("#1C2B2B") # Deep Forest (Headings & Body)
    c_text_secondary = colors.HexColor("#6B7F7F") # Teal Slate (Labels & Muted copy)
    c_rose_bg = colors.HexColor("#FFE8E8")     # Alert Rose Fill
    c_rose_text = colors.HexColor("#E53E3E")   # Alert Rose Text
    c_emerald_text = colors.HexColor("#047857")# Positive / Present green

    # Font Families with fallback support
    f_body = get_font_name("Nunito", "Helvetica")
    f_bold = get_font_name("Nunito-Bold", "Helvetica-Bold")
    f_heading = get_font_name("Poppins-Bold", "Helvetica-Bold")
    f_semi = get_font_name("Poppins-SemiBold", "Helvetica-Bold")
    f_mono = get_font_name("JetBrainsMono", "Courier")
    f_mono_bold = get_font_name("JetBrainsMono-Bold", "Courier-Bold")

    # Typography Styles
    company_title_style = ParagraphStyle(
        'CompTitle',
        fontName=f_heading,
        fontSize=13,
        leading=16,
        textColor=c_text_primary,
        alignment=TA_LEFT
    )
    company_sub_style = ParagraphStyle(
        'CompSub',
        fontName=f_body,
        fontSize=7,
        leading=9.5,
        textColor=c_text_secondary,
        alignment=TA_LEFT
    )
    statement_title_style = ParagraphStyle(
        'StateTitle',
        fontName=f_heading,
        fontSize=8.5,
        leading=11,
        textColor=c_text_secondary,
        alignment=TA_RIGHT
    )
    statement_meta_style = ParagraphStyle(
        'StateMeta',
        fontName=f_mono_bold,
        fontSize=8,
        leading=11,
        textColor=c_text_primary,
        alignment=TA_RIGHT
    )
    statement_date_style = ParagraphStyle(
        'StateDate',
        fontName=f_body,
        fontSize=7.5,
        leading=10,
        textColor=c_text_secondary,
        alignment=TA_RIGHT
    )
    ribbon_style = ParagraphStyle(
        'Ribbon',
        fontName=f_heading,
        fontSize=9,
        leading=12,
        textColor=colors.white,
        alignment=TA_CENTER
    )
    table_header_style = ParagraphStyle(
        'TableHead',
        fontName=f_heading,
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=TA_LEFT
    )
    table_header_right = ParagraphStyle(
        'TableHeadR',
        fontName=f_heading,
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=TA_RIGHT
    )
    section_subhead_style = ParagraphStyle(
        'SecSubHead',
        fontName=f_heading,
        fontSize=7,
        leading=9,
        textColor=c_teal
    )
    cell_label_style = ParagraphStyle(
        'CellLbl',
        fontName=f_bold,
        fontSize=7,
        leading=9,
        textColor=c_text_secondary
    )
    cell_value_style = ParagraphStyle(
        'CellVal',
        fontName=f_body,
        fontSize=7.5,
        leading=10,
        textColor=c_text_primary
    )
    cell_value_bold = ParagraphStyle(
        'CellValB',
        fontName=f_bold,
        fontSize=7.5,
        leading=10,
        textColor=c_text_primary
    )
    cell_mono_bold = ParagraphStyle(
        'CellMonoB',
        fontName=f_mono_bold,
        fontSize=7.5,
        leading=10,
        textColor=c_text_primary
    )
    cell_mono_right = ParagraphStyle(
        'CellMonoR',
        fontName=f_mono_bold,
        fontSize=7.5,
        leading=10,
        textColor=c_text_primary,
        alignment=TA_RIGHT
    )
    subtotal_label = ParagraphStyle(
        'SubtotalLbl',
        fontName=f_heading,
        fontSize=7.5,
        leading=10,
        textColor=c_text_primary
    )
    subtotal_amt_earn = ParagraphStyle(
        'SubtotalEarn',
        fontName=f_mono_bold,
        fontSize=8.5,
        leading=11,
        textColor=c_teal,
        alignment=TA_RIGHT
    )
    subtotal_amt_deduct = ParagraphStyle(
        'SubtotalDeduct',
        fontName=f_mono_bold,
        fontSize=8.5,
        leading=11,
        textColor=c_rose_text,
        alignment=TA_RIGHT
    )
    net_box_label = ParagraphStyle(
        'NetBoxLbl',
        fontName=f_heading,
        fontSize=8.5,
        leading=11,
        textColor=c_teal,
        alignment=TA_LEFT
    )
    net_box_sub = ParagraphStyle(
        'NetBoxSub',
        fontName=f_body,
        fontSize=7,
        leading=9,
        textColor=c_text_secondary,
        alignment=TA_LEFT
    )
    net_box_words = ParagraphStyle(
        'NetBoxWords',
        fontName=f_body,
        fontSize=7.5,
        leading=9.5,
        textColor=c_text_primary,
        alignment=TA_LEFT
    )
    net_box_amount = ParagraphStyle(
        'NetBoxAmt',
        fontName=f_mono_bold,
        fontSize=15,
        leading=18,
        textColor=c_teal,
        alignment=TA_RIGHT
    )
    footer_text_style = ParagraphStyle(
        'FooterTxt',
        fontName=f_body,
        fontSize=6.5,
        leading=8.5,
        textColor=c_text_secondary,
        alignment=TA_LEFT
    )
    footer_sign_style = ParagraphStyle(
        'FooterSgn',
        fontName=f_heading,
        fontSize=7.5,
        leading=10,
        textColor=c_text_primary,
        alignment=TA_RIGHT
    )

    elements = []
    
    # 1. Company Information & Header
    company_name = company.name if company and company.name else "TURTU HRMS"
    company_addr = company.address if company and company.address else "Karnataka, India"
    currency = company.currency_symbol if company and company.currency_symbol else "₹"
    month_name = get_month_name(payslip.month)
    slip_no = f"PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}"
    
    header_left_text = [
        Paragraph(f"<b>{company_name.upper()}</b>", company_title_style),
        Spacer(1, 1),
        Paragraph(company_addr, company_sub_style),
        Paragraph("CIN: U72200KA2024PTC123456 • GSTIN/TAX: 29TURTU1234F1Z5 • PAN: TURTU1234F", company_sub_style),
        Paragraph("Corporate HR & Payroll Division • support@turtu.in", company_sub_style)
    ]

    logo_path = os.path.abspath("static/images/icon.jpeg")
    if not os.path.exists(logo_path):
        logo_path = os.path.abspath("static/images/logo.png")

    if os.path.exists(logo_path):
        try:
            logo_img = RLImage(logo_path, width=44, height=44)
            brand_table = Table([[logo_img, header_left_text]], colWidths=[52, 285])
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
    
    disbursement_str = payslip.generated_on.strftime('%B %d, %Y') if hasattr(payslip.generated_on, 'strftime') and payslip.generated_on else (str(payslip.generated_on) if payslip.generated_on else "End of Month")
    header_right = [
        Paragraph("<b>CONFIDENTIAL SALARY STATEMENT</b>", statement_title_style),
        Spacer(1, 1),
        Paragraph(f"<b>Slip No:</b> {slip_no}", statement_meta_style),
        Paragraph(f"<b>Disbursement:</b> {disbursement_str}", statement_date_style),
        Paragraph(f"<b>Status:</b> {payslip.status.upper()}", statement_date_style)
    ]
    
    header_table = Table([[header_left, header_right]], colWidths=[337, 206])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2, color=c_dark, spaceBefore=0, spaceAfter=5))

    # 2. Payslip Month Banner (Gradient Look / Dark Forest)
    ribbon_data = [[Paragraph(f"PAYSLIP FOR THE MONTH OF {month_name.upper()} {payslip.year}", ribbon_style)]]
    ribbon_table = Table(ribbon_data, colWidths=[543])
    ribbon_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_dark),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(ribbon_table)
    elements.append(Spacer(1, 4))

    # 3. Employee and Bank Metadata Grid (2-Column Dashboard Box Style)
    dept_name = employee.department.name if employee.department else (employee.department or "Operations")
    desig_title = employee.designation.title if employee.designation else (employee.designation or "Staff")
    emp_bank = employee.bank_account.bank_name if employee.bank_account and employee.bank_account.bank_name else "HDFC Bank"
    emp_acc = mask_account_number(employee.bank_account.account_number if employee.bank_account else "")
    emp_ifsc = employee.bank_account.ifsc_code if employee.bank_account and employee.bank_account.ifsc_code else "HDFC0001092"
    emp_doj = str(employee.joining_date) if employee.joining_date else "N/A"
    emp_pan = employee.profile.pan_number if employee.profile and employee.profile.pan_number else "ABCDE1234F"

    meta_left = [
        [Paragraph("<b>EMPLOYEE IDENTIFICATION</b>", section_subhead_style), Paragraph("", cell_value_style)],
        [Paragraph("Employee Name:", cell_label_style), Paragraph(f"<b>{employee.name}</b>", cell_value_bold)],
        [Paragraph("Employee ID:", cell_label_style), Paragraph(f"EMP-{employee.id:04d}", cell_mono_bold)],
        [Paragraph("Department:", cell_label_style), Paragraph(str(dept_name), cell_value_style)],
        [Paragraph("Designation:", cell_label_style), Paragraph(str(desig_title), cell_value_style)],
        [Paragraph("Date of Joining:", cell_label_style), Paragraph(str(emp_doj), cell_value_style)],
    ]
    meta_right = [
        [Paragraph("<b>PAYMENT & STATUTORY DETAILS</b>", section_subhead_style), Paragraph("", cell_value_style)],
        [Paragraph("Bank Name:", cell_label_style), Paragraph(str(emp_bank), cell_value_style)],
        [Paragraph("Bank Account No:", cell_label_style), Paragraph(str(emp_acc), cell_mono_bold)],
        [Paragraph("IFSC / Branch Code:", cell_label_style), Paragraph(str(emp_ifsc), cell_mono_bold)],
        [Paragraph("PAN / Tax ID:", cell_label_style), Paragraph(str(emp_pan), cell_mono_bold)],
        [Paragraph("PF / UAN No:", cell_label_style), Paragraph("100982348123", cell_mono_bold)],
    ]

    t_meta_left = Table(meta_left, colWidths=[90, 175])
    t_meta_left.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, c_light),
    ]))

    t_meta_right = Table(meta_right, colWidths=[90, 175])
    t_meta_right.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, c_light),
    ]))

    meta_container = Table([[t_meta_left, t_meta_right]], colWidths=[271.5, 271.5])
    meta_container.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_wash),
        ('BOX', (0,0), (-1,-1), 0.75, c_light),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_light),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(meta_container)
    elements.append(Spacer(1, 4))

    # 4. Attendance Summary Ribbon
    lop_days = max(0.0, payslip.payable_days - payslip.days_worked)
    att_label_style = ParagraphStyle('AttLbl', fontName=f_bold, fontSize=6.5, leading=8.5, textColor=c_text_secondary, alignment=TA_CENTER)
    att_val_style = ParagraphStyle('AttVal', fontName=f_mono_bold, fontSize=8, leading=10, textColor=c_text_primary, alignment=TA_CENTER)
    att_val_worked = ParagraphStyle('AttValW', fontName=f_mono_bold, fontSize=8, leading=10, textColor=c_emerald_text, alignment=TA_CENTER)
    att_val_lop = ParagraphStyle('AttValL', fontName=f_mono_bold, fontSize=8, leading=10, textColor=c_rose_text, alignment=TA_CENTER)
    att_val_mode = ParagraphStyle('AttValM', fontName=f_bold, fontSize=7.5, leading=10, textColor=c_teal, alignment=TA_CENTER)

    att_data = [[
        [Paragraph("STANDARD WORKING DAYS", att_label_style), Paragraph(str(payslip.payable_days), att_val_style)],
        [Paragraph("DAYS WORKED / PRESENT", att_label_style), Paragraph(f"{payslip.days_worked:.1f}", att_val_worked)],
        [Paragraph("LOSS OF PAY (LOP) / LEAVE", att_label_style), Paragraph(f"{lop_days:.1f}", att_val_lop)],
        [Paragraph("PAYMENT MODE", att_label_style), Paragraph("Direct Bank Transfer", att_val_mode)],
    ]]
    att_table = Table(att_data, colWidths=[135.75, 135.75, 135.75, 135.75])
    att_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_mist),
        ('BOX', (0,0), (-1,-1), 0.5, c_light),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_light),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(att_table)
    elements.append(Spacer(1, 4))

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
            Paragraph(f"{payslip.basic:,.2f}", cell_mono_right),
            Paragraph("Employee Provident Fund (PF)", cell_value_style),
            Paragraph(f"{payslip.pf:,.2f}", cell_mono_right)
        ],
        [
            Paragraph("House Rent Allowance (HRA)", cell_value_style),
            Paragraph(f"{payslip.hra:,.2f}", cell_mono_right),
            Paragraph("Professional Tax (PT) / TDS", cell_value_style),
            Paragraph(f"{payslip.tax:,.2f}", cell_mono_right)
        ],
        [
            Paragraph("Special & Conveyance Allowance", cell_value_style),
            Paragraph(f"{payslip.allowances:,.2f}", cell_mono_right),
            Paragraph("Other Recoveries / Advance", cell_value_style),
            Paragraph(f"{payslip.other_deductions:,.2f}", cell_mono_right)
        ],
        [
            Paragraph("Performance Incentive / Bonus", cell_value_style),
            Paragraph(f"{payslip.bonus:,.2f}", cell_mono_right),
            Paragraph("—", ParagraphStyle('Dash', fontName=f_body, fontSize=7.5, textColor=c_text_secondary)),
            Paragraph("0.00", ParagraphStyle('DashAmt', fontName=f_mono_bold, fontSize=7.5, textColor=c_text_secondary, alignment=TA_RIGHT))
        ],
        # Subtotals Row
        [
            Paragraph("<b>TOTAL GROSS EARNINGS (A)</b>", subtotal_label),
            Paragraph(f"<b>{currency} {total_earnings:,.2f}</b>", subtotal_amt_earn),
            Paragraph("<b>TOTAL DEDUCTIONS (B)</b>", ParagraphStyle('DeductHead', parent=subtotal_label, textColor=c_rose_text)),
            Paragraph(f"<b>{currency} {total_deductions:,.2f}</b>", subtotal_amt_deduct)
        ]
    ]

    breakdown_table = Table(breakdown_data, colWidths=[191.5, 80, 191.5, 80])
    breakdown_table.setStyle(TableStyle([
        # Headers
        ('BACKGROUND', (0,0), (1,0), c_dark),
        ('BACKGROUND', (2,0), (3,0), c_dark),
        ('TOPPADDING', (0,0), (-1,0), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,0), 3.5),
        
        # Rows
        ('BACKGROUND', (0,1), (-1,-2), colors.white),
        ('ROWBACKGROUNDS', (0,1), (1,-2), [colors.white, c_wash]),
        ('ROWBACKGROUNDS', (2,1), (3,-2), [colors.white, c_wash]),
        ('TOPPADDING', (0,1), (-1,-2), 3),
        ('BOTTOMPADDING', (0,1), (-1,-2), 3),

        # Subtotals Row
        ('BACKGROUND', (0,-1), (1,-1), c_wash),
        ('BACKGROUND', (2,-1), (3,-1), c_rose_bg),
        ('TOPPADDING', (0,-1), (-1,-1), 4),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 4),

        # Grid lines
        ('BOX', (0,0), (-1,-1), 0.75, c_light),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_light),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(breakdown_table)
    elements.append(Spacer(1, 4))

    # 6. Net Take-Home Salary Highlight Box (Exact Turtu Theme Styling)
    words = number_to_words(payslip.net_salary, currency)
    net_content = [
        [
            [
                Paragraph("<b>NET TAKE-HOME SALARY (A - B)</b>", net_box_label),
                Paragraph("Disbursed via Electronic Bank Transfer (NEFT/RTGS)", net_box_sub),
                Spacer(1, 1.5),
                Paragraph(f"<b>Amount in Words:</b> <i>{words}</i>", net_box_words)
            ],
            [
                Paragraph(f"<b>{currency} {payslip.net_salary:,.2f}</b>", net_box_amount),
            ]
        ]
    ]
    net_table = Table(net_content, colWidths=[363, 180])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_mist),
        ('BOX', (0,0), (-1,-1), 1.25, c_teal),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(net_table)
    elements.append(Spacer(1, 10))

    # 7. Official Footer & Authorized Signatory Block
    disclaimer = [
        Paragraph("<b>Official Verified Document</b>", ParagraphStyle('DisclH', parent=cell_value_bold, textColor=c_teal)),
        Paragraph("*This is a computer-generated official salary certificate issued by the TURTU HRMS platform. "
                  "It does not require a physical handwritten signature.", footer_text_style),
        Paragraph(f"SECURITY REF: AUTH-PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}-VERIFIED", ParagraphStyle('SecHash', parent=footer_text_style, fontName=f_mono, fontSize=5.5))
    ]
    signatory = [
        Paragraph("____________________________", footer_sign_style),
        Paragraph("<b>Authorized Signatory</b>", footer_sign_style),
        Paragraph(f"For {company_name}", ParagraphStyle('SubComp', parent=footer_sign_style, fontSize=6.5, textColor=c_text_secondary))
    ]

    footer_table = Table([[disclaimer, signatory]], colWidths=[363, 180])
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
