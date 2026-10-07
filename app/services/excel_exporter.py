import datetime
from io import BytesIO
from typing import List, Optional, Any, Dict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from fastapi.responses import Response

from app.templates_config import format_emp_code


# =========================================================================
# Shared Excel Styling & Helpers
# =========================================================================

TEAL_HEADER_FILL = PatternFill(start_color="008080", end_color="008080", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="008080")
SUBTITLE_FONT = Font(name="Calibri", size=10, italic=True, color="475569")
BOLD_FONT = Font(name="Calibri", size=10, bold=True, color="0F172A")
REGULAR_FONT = Font(name="Calibri", size=10, color="1E293B")
MUTED_FONT = Font(name="Calibri", size=9, color="64748B")

THIN_BORDER = Border(
    left=Side(style="thin", color="CBD5E1"),
    right=Side(style="thin", color="CBD5E1"),
    top=Side(style="thin", color="CBD5E1"),
    bottom=Side(style="thin", color="CBD5E1"),
)
BOTTOM_DOUBLE_BORDER = Border(
    left=Side(style="thin", color="CBD5E1"),
    right=Side(style="thin", color="CBD5E1"),
    top=Side(style="thin", color="CBD5E1"),
    bottom=Side(style="double", color="0F172A"),
)
ZEBRA_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
TOTAL_ROW_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")


def style_table_headers(ws, row_idx: int, num_cols: int, bg_color: str = "008080"):
    """Styles the header row with corporate background, bold white text, and center alignment."""
    fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
    ws.row_dimensions[row_idx].height = 26
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.fill = fill
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def autofit_sheet_columns(ws, min_width: int = 12, max_width: int = 50, skip_rows: int = 0):
    """Dynamically calculates maximum string length in each column and sets column dimensions."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row <= skip_rows:
                continue
            val = str(cell.value or "")
            if "\n" in val:
                lines = val.split("\n")
                line_len = max(len(l) for l in lines)
                if line_len > max_len:
                    max_len = line_len
            else:
                if len(val) > max_len:
                    max_len = len(val)
        ws.column_dimensions[col_letter].width = max(min(max_len + 4, max_width), min_width)


def build_excel_response(wb: openpyxl.Workbook, filename: str) -> Response:
    """Serializes workbook to in-memory bytes and returns an HTTP attachment response."""
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    if not filename.endswith(".xlsx"):
        filename += ".xlsx"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


# =========================================================================
# 1. EMPLOYEES DIRECTORY EXPORT & SAMPLE TEMPLATE
# =========================================================================

def export_employees_excel(employees: List[Any], company: Optional[Any] = None) -> Response:
    """Exports employee roster to Excel with corporate formatting."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employees Directory"
    ws.views.sheetView[0].showGridLines = True

    # Title Block
    comp_name = company.name if company and company.name else "Company HRMS"
    ws.merge_cells("A1:K1")
    ws["A1"] = f"{comp_name} — Workforce & Employee Directory"
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:K2")
    ws["A2"] = f"Exported on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Total Active Records: {len(employees)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Employee Code",
        "Full Name",
        "Work Email",
        "Phone Number",
        "Department",
        "Designation",
        "System Role",
        "Date of Joining",
        "Base Salary",
        "Status",
        "Emergency Contact",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "A5"

    currency = company.currency_symbol if company and company.currency_symbol else "₹"

    for idx, emp in enumerate(employees, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        emp_code = format_emp_code(emp, company)
        dept_name = emp.department.name if (emp and emp.department) else "General"
        designation = emp.designation.title if (getattr(emp, "designation", None) and hasattr(emp.designation, "title")) else (getattr(emp, "role", "Employee") or "Employee").replace("_", " ").title()
        status_text = "Active" if emp.is_active else "Inactive"
        
        emergency_name = getattr(emp, "emergency_contact_name", None) or ""
        emergency_phone = getattr(emp, "emergency_contact", None) or getattr(emp, "emergency_contact_phone", None) or ""
        if emergency_name and emergency_phone:
            emergency_str = f"{emergency_name} ({emergency_phone})"
        elif emergency_phone:
            emergency_str = emergency_phone
        elif emergency_name:
            emergency_str = emergency_name
        else:
            emergency_str = "—"

        joining_date = getattr(emp, "joining_date", None) or getattr(emp, "date_of_joining", None)
        joining_str = joining_date.strftime("%Y-%m-%d") if joining_date else "—"
        phone_str = getattr(emp, "phone_number", None) or getattr(emp, "phone", None) or "—"

        row_data = [
            emp_code,
            emp.name,
            emp.email,
            phone_str,
            dept_name,
            designation,
            emp.role.replace("_", " ").title() if emp.role else "Employee",
            joining_str,
            emp.base_salary if emp.base_salary is not None else 0.0,
            status_text,
            emergency_str,
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            # Specific column alignments and formats
            if col_idx in [1, 7, 8, 10]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 9:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = f'"{currency}" #,##0.00'
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    today_str = datetime.date.today().strftime("%Y%m%d")
    return build_excel_response(wb, f"employees_directory_{today_str}.xlsx")


def export_employee_sample_template() -> Response:
    """Generates an official sample import template for bulk onboarding."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employee Import Template"
    ws.views.sheetView[0].showGridLines = True

    # Instructions Block
    ws.merge_cells("A1:G1")
    ws["A1"] = "EMPLOYEE BULK IMPORT SPREADSHEET TEMPLATE"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 22

    ws.merge_cells("A2:G2")
    ws["A2"] = "Instructions: Fill employee records starting from Row 4. Do NOT modify header column names in Row 3."
    ws["A2"].font = SUBTITLE_FONT

    headers = [
        "Employee ID (Optional)",
        "Full Name *",
        "Email Address *",
        "Phone Number",
        "Department Name",
        "Designation",
        "System Role (employee/manager/hr/admin)",
    ]

    header_row = 3
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers), bg_color="0D9488")
    ws.freeze_panes = "A4"

    # Sample demo rows
    samples = [
        ["EMP-0001", "Aarav Sharma", "aarav.sharma@example.com", "+91 9876543210", "Engineering", "Software Engineer", "employee"],
        ["EMP-0002", "Diya Patel", "diya.patel@example.com", "+91 9876543211", "Human Resources", "HR Executive", "hr"],
        ["EMP-0003", "Rohan Mehta", "rohan.mehta@example.com", "+91 9876543212", "Marketing", "Marketing Manager", "manager"],
    ]

    for idx, sample in enumerate(samples, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        for col_idx, val in enumerate(sample, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if col_idx in [1, 7]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=2)
    return build_excel_response(wb, "sample_employee_import_template.xlsx")


# =========================================================================
# 2. PAYROLL REGISTER EXPORT
# =========================================================================

def export_payroll_excel(payslips: List[Any], company: Optional[Any] = None, month: Optional[int] = None, year: Optional[int] = None) -> Response:
    """Exports comprehensive monthly salary and banking register with summary totals."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payroll Register"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"
    currency = company.currency_symbol if company and company.currency_symbol else "₹"
    
    month_names = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    period_str = f"{month_names[month]} {year}" if (month and year and 1 <= month <= 12) else "Consolidated"

    # Header Titles
    ws.merge_cells("A1:N1")
    ws["A1"] = f"{comp_name} — Monthly Payroll & Bank Disbursement Register"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:N2")
    ws["A2"] = f"Pay Period: {period_str} • Generated On: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Total Payslips: {len(payslips)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Slip ID",
        "Employee Code",
        "Employee Name",
        "Department",
        "Bank Name",
        "Account Number",
        "IFSC Code",
        "Pay Period",
        "Paid Days",
        "Gross Pay",
        "Total Deductions",
        "Net Payable",
        "Status",
        "Payment Date",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers), bg_color="008080")
    ws.freeze_panes = "A5"

    total_gross = 0.0
    total_deductions = 0.0
    total_net = 0.0

    for idx, slip in enumerate(payslips, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        emp = slip.employee
        emp_code = format_emp_code(emp or slip.employee_id, company)
        dept_name = emp.department.name if emp and emp.department else "General"
        
        # Calculate gross, deductions, and net accurately from Payslip model fields
        if hasattr(slip, "basic"):
            gross = float((getattr(slip, "basic", 0.0) or 0.0) + (getattr(slip, "hra", 0.0) or 0.0) + (getattr(slip, "allowances", 0.0) or 0.0) + (getattr(slip, "bonus", 0.0) or 0.0))
            ded = float((getattr(slip, "pf", 0.0) or 0.0) + (getattr(slip, "tax", 0.0) or 0.0) + (getattr(slip, "other_deductions", 0.0) or 0.0))
            net = float(getattr(slip, "net_salary", None) if getattr(slip, "net_salary", None) is not None else (gross - ded))
        else:
            gross = float(getattr(slip, "gross_pay", 0.0) or 0.0)
            ded = float(getattr(slip, "total_deductions", 0.0) or 0.0)
            net = float(getattr(slip, "net_pay", 0.0) or (gross - ded))

        total_gross += gross
        total_deductions += ded
        total_net += net

        slip_period = f"{month_names[slip.month]} {slip.year}" if (slip.month and 1 <= slip.month <= 12) else "—"
        paid_days_val = getattr(slip, "days_worked", None) or getattr(slip, "payable_days", None) or 30
        gen_date = getattr(slip, "generated_on", None) or getattr(slip, "payment_date", None)

        row_data = [
            slip.id,
            emp_code,
            emp.name if emp else "Unknown",
            dept_name,
            getattr(emp, "bank_name", None) or "—",
            getattr(emp, "account_number", None) or "—",
            getattr(emp, "ifsc_code", None) or "—",
            slip_period,
            paid_days_val,
            gross,
            ded,
            net,
            slip.status.title() if slip.status else "Draft",
            gen_date.strftime("%Y-%m-%d") if gen_date else "—",
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 2, 8, 9, 13, 14]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [10, 11, 12]:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = f'"{currency}" #,##0.00'
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Bottom Summary Row
    summary_row_idx = header_row + len(payslips) + 1
    ws.row_dimensions[summary_row_idx].height = 24
    ws.merge_cells(start_row=summary_row_idx, start_column=1, end_row=summary_row_idx, end_column=9)
    ws.cell(row=summary_row_idx, column=1, value="TOTAL CONSOLIDATED PAYOUT:").font = BOLD_FONT
    ws.cell(row=summary_row_idx, column=1).alignment = Alignment(horizontal="right", vertical="center")

    for c in range(1, 10):
        ws.cell(row=summary_row_idx, column=c).fill = TOTAL_ROW_FILL
        ws.cell(row=summary_row_idx, column=c).border = BOTTOM_DOUBLE_BORDER

    # Gross Total
    cell_g = ws.cell(row=summary_row_idx, column=10, value=total_gross)
    cell_g.font = BOLD_FONT
    cell_g.fill = TOTAL_ROW_FILL
    cell_g.alignment = Alignment(horizontal="right", vertical="center")
    cell_g.number_format = f'"{currency}" #,##0.00'
    cell_g.border = BOTTOM_DOUBLE_BORDER

    # Deductions Total
    cell_d = ws.cell(row=summary_row_idx, column=11, value=total_deductions)
    cell_d.font = BOLD_FONT
    cell_d.fill = TOTAL_ROW_FILL
    cell_d.alignment = Alignment(horizontal="right", vertical="center")
    cell_d.number_format = f'"{currency}" #,##0.00'
    cell_d.border = BOTTOM_DOUBLE_BORDER

    # Net Total
    cell_n = ws.cell(row=summary_row_idx, column=12, value=total_net)
    cell_n.font = Font(name="Calibri", size=11, bold=True, color="008080")
    cell_n.fill = TOTAL_ROW_FILL
    cell_n.alignment = Alignment(horizontal="right", vertical="center")
    cell_n.number_format = f'"{currency}" #,##0.00'
    cell_n.border = BOTTOM_DOUBLE_BORDER

    for c in [13, 14]:
        ws.cell(row=summary_row_idx, column=c, value="").fill = TOTAL_ROW_FILL
        ws.cell(row=summary_row_idx, column=c).border = BOTTOM_DOUBLE_BORDER

    autofit_sheet_columns(ws, skip_rows=3)
    filename = f"payroll_register_{year}_{month:02d}.xlsx" if (year and month) else "payroll_register_export.xlsx"
    return build_excel_response(wb, filename)


# =========================================================================
# 3. ATTENDANCE LOGS & 31-DAY MONTHLY MATRIX
# =========================================================================

def export_attendance_excel(logs_data: List[Dict[str, Any]], company: Optional[Any] = None, date_filter: Optional[str] = None) -> Response:
    """Exports daily or filtered attendance punch logs with durations and geofence flags."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Logs"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"
    filter_label = f"Date Filter: {date_filter}" if date_filter else "Consolidated Punch History"

    ws.merge_cells("A1:J1")
    ws["A1"] = f"{comp_name} — Attendance Punch Logs"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:J2")
    ws["A2"] = f"{filter_label} • Generated On: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Records: {len(logs_data)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Date",
        "Employee Code",
        "Employee Name",
        "Department",
        "First Check-In",
        "Last Check-Out",
        "Total Hours",
        "Status",
        "Overridden",
        "Manager Notes",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "A5"

    for idx, item in enumerate(logs_data, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20

        emp = item.get("employee")
        emp_code = format_emp_code(emp, company)
        dept_name = emp.department.name if (emp and emp.department) else "General"

        row_data = [
            str(item.get("date", "—")),
            emp_code,
            emp.name if emp else "Unknown",
            dept_name,
            item.get("in_time_str", "—"),
            item.get("out_time_str", "—"),
            item.get("hours_str", "0.0h"),
            item.get("status_label", "Present"),
            "Yes" if item.get("is_overridden") else "No",
            item.get("override_reason", "—") or "—",
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 2, 5, 6, 7, 8, 9]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    file_suffix = f"_{date_filter}" if date_filter else f"_{datetime.date.today().strftime('%Y%m%d')}"
    return build_excel_response(wb, f"attendance_logs{file_suffix}.xlsx")


def export_attendance_monthly_matrix_excel(
    employees: List[Any],
    grouped_matrix: Dict[int, Dict[str, Any]],
    month: int,
    year: int,
    company: Optional[Any] = None
) -> Response:
    """Exports a full 31-day timesheet matrix with daily status codes and monthly aggregations."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Matrix {month:02d}-{year}"
    ws.views.sheetView[0].showGridLines = True

    import calendar
    _, days_in_month = calendar.monthrange(year, month)
    month_names = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    comp_name = company.name if company and company.name else "Company HRMS"
    total_cols = 3 + days_in_month + 5

    # Top Title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws["A1"] = f"{comp_name} — Monthly Attendance Matrix ({month_names[month]} {year})"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    ws["A2"] = f"Standard 31-Day Shift Ledger • Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    # Headers
    headers = ["Code", "Employee Name", "Department"]
    for day in range(1, days_in_month + 1):
        headers.append(f"D{day}")
    headers.extend(["Present (P)", "Half Day (HD)", "WFH (W)", "Leaves (L)", "Absent (A)"])

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "D5"

    for idx, emp in enumerate(employees, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        emp_code = format_emp_code(emp, company)
        dept_name = emp.department.name if emp.department else "General"
        
        emp_records = grouped_matrix.get(emp.id, {})
        daily_map = emp_records.get("days", {})

        p_count = 0
        hd_count = 0
        wfh_count = 0
        leave_count = 0
        absent_count = 0

        row_data = [emp_code, emp.name, dept_name]
        for d in range(1, days_in_month + 1):
            d_str = f"{year}-{month:02d}-{d:02d}"
            code = daily_map.get(d_str, "—")
            row_data.append(code)

            if code == "P": p_count += 1
            elif code == "HD": hd_count += 1
            elif code in ["W", "WFH"]: wfh_count += 1
            elif code == "L": leave_count += 1
            elif code == "A": absent_count += 1

        row_data.extend([p_count, hd_count, wfh_count, leave_count, absent_count])

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1] or col_idx > 3:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, min_width=5, max_width=30, skip_rows=3)
    return build_excel_response(wb, f"attendance_matrix_{year}_{month:02d}.xlsx")


# =========================================================================
# 4. LEAVES & ANNUAL QUOTA BALANCES EXPORT
# =========================================================================

def export_leaves_excel(
    leaves_data: List[Any],
    company: Optional[Any] = None,
    year: Optional[int] = None,
    status_filter: Optional[str] = None
) -> Response:
    """Exports leave and remote shift application ledger."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leaves Register"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"
    yr_label = f"Year {year}" if year else "All Years"
    st_label = f"Status: {status_filter.title()}" if (status_filter and status_filter != 'all') else "All Statuses"

    ws.merge_cells("A1:K1")
    ws["A1"] = f"{comp_name} — Leave Applications & Approvals Ledger"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:K2")
    ws["A2"] = f"{yr_label} • {st_label} • Generated On: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Records: {len(leaves_data)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Req ID",
        "Employee Code",
        "Employee Name",
        "Department",
        "Leave Category",
        "Start Date",
        "End Date",
        "Total Days",
        "Reason / Objectives",
        "Status",
        "Applied Date",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "A5"

    for idx, l in enumerate(leaves_data, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        emp = l.employee
        emp_code = format_emp_code(emp, company)
        dept_name = emp.department.name if (emp and emp.department) else "General"
        cat_name = l.leave_type.name if hasattr(l, "leave_type") and l.leave_type else "WFH / Remote"

        row_data = [
            l.id,
            emp_code,
            emp.name if emp else "Unknown",
            dept_name,
            cat_name,
            str(l.start_date),
            str(l.end_date),
            l.total_days,
            l.reason or "—",
            l.status.replace("_", " ").title() if l.status else "Pending",
            l.created_at.strftime("%Y-%m-%d") if getattr(l, "created_at", None) else "—",
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 2, 6, 7, 8, 10, 11]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    return build_excel_response(wb, f"leave_applications_{year or 'all'}.xlsx")


def export_leave_balances_excel(balances_data: List[Any], company: Optional[Any] = None, year: Optional[int] = None) -> Response:
    """Exports staff annual leave entitlement quotas, availed days, and remaining balances."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leave Balances & Quotas"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"
    yr = year or datetime.date.today().year

    ws.merge_cells("A1:H1")
    ws["A1"] = f"{comp_name} — Staff Leave Quotas & Entitlement Balances"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:H2")
    ws["A2"] = f"Fiscal Year: {yr} • Generated On: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Total Entries: {len(balances_data)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Employee Code",
        "Employee Name",
        "Department",
        "Gender",
        "Leave Category",
        "Annual Quota",
        "Availed Days",
        "Remaining Balance",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "A5"

    for idx, b in enumerate(balances_data, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        emp = b.employee
        emp_code = format_emp_code(emp, company)
        dept_name = emp.department.name if (emp and emp.department) else "General"
        cat_name = b.leave_type.name if b.leave_type else "General Leave"
        gender_str = emp.gender.title() if (emp and emp.gender) else "—"

        total_alloc = float(getattr(b, "total_allocated", 0.0) or 0.0)
        used_val = float(getattr(b, "used_days", None) if getattr(b, "used_days", None) is not None else (getattr(b, "used", 0.0) or 0.0))
        rem_val = float(getattr(b, "remaining_days", None) if getattr(b, "remaining_days", None) is not None else (getattr(b, "remaining", None) if getattr(b, "remaining", None) is not None else max(0.0, total_alloc - used_val)))

        row_data = [
            emp_code,
            emp.name if emp else "Unknown",
            dept_name,
            gender_str,
            cat_name,
            total_alloc,
            used_val,
            rem_val,
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 4, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    return build_excel_response(wb, f"staff_leave_balances_{yr}.xlsx")


# =========================================================================
# 5. KYC & DOCUMENT COMPLIANCE EXPORT
# =========================================================================

def export_kyc_compliance_excel(compliance_data: List[Dict[str, Any]], company: Optional[Any] = None) -> Response:
    """Exports company-wide document verification and KYC compliance audit."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "KYC Compliance Report"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"

    ws.merge_cells("A1:H1")
    ws["A1"] = f"{comp_name} — Workforce KYC & Document Compliance Audit"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:H2")
    ws["A2"] = f"Audit Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Total Workforce Audited: {len(compliance_data)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Employee Code",
        "Employee Name",
        "Department",
        "Compliance %",
        "Total Required",
        "Verified",
        "Pending Review",
        "Missing Paperwork Slots",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "A5"

    for idx, item in enumerate(compliance_data, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        emp = item.get("employee")
        emp_code = format_emp_code(emp, company)
        dept_name = emp.department.name if (emp and emp.department) else "General"

        missing_list = item.get("missing_slots", [])
        missing_str = ", ".join(missing_list) if missing_list else "None (Fully Verified)"

        row_data = [
            emp_code,
            emp.name if emp else "Unknown",
            dept_name,
            f"{item.get('compliance_percent', 0)}%",
            item.get("mandatory_total", 0),
            item.get("mandatory_verified", 0),
            item.get("pending_review", 0),
            missing_str,
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 4, 5, 6, 7]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    return build_excel_response(wb, f"kyc_compliance_audit_{datetime.date.today().strftime('%Y%m%d')}.xlsx")


# =========================================================================
# 6. SECURITY & AUDIT TRAIL EXPORT
# =========================================================================

def export_audit_logs_excel(logs: List[Any], company: Optional[Any] = None) -> Response:
    """Exports security and administrative audit trail with modification diffs."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Security Audit Trail"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"

    ws.merge_cells("A1:G1")
    ws["A1"] = f"{comp_name} — Administrative Security & Activity Audit Trail"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:G2")
    ws["A2"] = f"Immutable Audit Export • Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Records: {len(logs)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Log ID",
        "Timestamp (IST)",
        "Actor Email",
        "Action Type",
        "Target Entity",
        "Previous State (Before Diff)",
        "Updated State (After Diff)",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers), bg_color="0F766E")
    ws.freeze_panes = "A5"

    for idx, log in enumerate(logs, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        entity_str = f"{log.entity} #{log.entity_id}" if log.entity_id else (log.entity or "—")

        row_data = [
            log.id,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "—",
            log.actor_email or "System",
            log.action.replace("_", " ").title() if log.action else "—",
            entity_str,
            log.old_value or "—",
            log.new_value or "—",
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 2, 4, 5]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    return build_excel_response(wb, f"audit_trail_export_{datetime.date.today().strftime('%Y%m%d')}.xlsx")


# =========================================================================
# 7. DEPARTMENTS & ORGANIZATION STRUCTURE EXPORT
# =========================================================================

def export_departments_excel(departments: List[Any], company: Optional[Any] = None) -> Response:
    """Exports corporate business units, HODs, designations, and headcounts."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Departments Master"
    ws.views.sheetView[0].showGridLines = True

    comp_name = company.name if company and company.name else "Company HRMS"

    ws.merge_cells("A1:F1")
    ws["A1"] = f"{comp_name} — Departments & Organization Hierarchy"
    ws["A1"].font = TITLE_FONT
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:F2")
    ws["A2"] = f"Generated On: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Total Departments: {len(departments)}"
    ws["A2"].font = SUBTITLE_FONT
    ws.row_dimensions[2].height = 18

    headers = [
        "Dept ID",
        "Department Name",
        "Department Code",
        "Head of Department (HOD)",
        "Active Headcount",
        "Created Date",
    ]

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    style_table_headers(ws, header_row, len(headers))
    ws.freeze_panes = "A5"

    for idx, d in enumerate(departments, start=1):
        row_idx = header_row + idx
        ws.row_dimensions[row_idx].height = 20
        hod_name = d.manager.name if hasattr(d, "manager") and d.manager else "Unassigned"
        headcount = len(d.employees) if hasattr(d, "employees") and d.employees else 0

        row_data = [
            d.id,
            d.name,
            getattr(d, "code", "") or "—",
            hod_name,
            headcount,
            d.created_at.strftime("%Y-%m-%d") if getattr(d, "created_at", None) else "—",
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = REGULAR_FONT
            cell.border = THIN_BORDER
            if idx % 2 == 0:
                cell.fill = ZEBRA_FILL

            if col_idx in [1, 3, 5, 6]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    autofit_sheet_columns(ws, skip_rows=3)
    return build_excel_response(wb, f"departments_roster_{datetime.date.today().strftime('%Y%m%d')}.xlsx")
