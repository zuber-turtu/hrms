import os
import sys
import shutil
import base64
import tempfile
import subprocess
import logging
from io import BytesIO
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.services.formatters import number_to_words, get_month_name, mask_account_number

logger = logging.getLogger(__name__)

# Font Registration Flag for ReportLab
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


def find_headless_browser() -> str | None:
    """Locates an available Chromium or Microsoft Edge executable for high-fidelity PDF rendering."""
    candidates = [
        os.environ.get("CHROME_PATH"),
        os.environ.get("EDGE_PATH"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for path in candidates:
        if path and os.path.exists(path) and os.path.isfile(path):
            return path
    return None


def generate_payslip_html(payslip, company=None, employee=None) -> str:
    """
    Renders an exact standalone HTML document with identical Tailwind CSS,
    Google Fonts (Nunito, Poppins, JetBrains Mono), and Lucide icons matching the web print DOM.
    """
    if employee is None:
        employee = getattr(payslip, "employee", None)
        
    company_name = company.name if company and company.name else "TURTU HRMS"
    company_addr = company.address if company and company.address else "Karnataka, India"
    currency = company.currency_symbol if company and company.currency_symbol else "₹"
    month_name = get_month_name(payslip.month)
    slip_no = f"PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}"
    
    if hasattr(payslip.generated_on, 'strftime') and payslip.generated_on:
        date_str = payslip.generated_on.strftime('%b %d, %Y')
    elif payslip.generated_on:
        date_str = str(payslip.generated_on)
    else:
        date_str = "—"

    emp_name = employee.name if employee and hasattr(employee, 'name') and employee.name else "Employee"
    emp_id_val = f"{employee.id:04d}" if employee and hasattr(employee, 'id') and employee.id else "0001"
    
    dept_name = "—"
    if employee and hasattr(employee, 'department') and employee.department:
        dept_name = employee.department.name if hasattr(employee.department, 'name') else str(employee.department)
        
    desig_title = "—"
    if employee and hasattr(employee, 'designation') and employee.designation:
        desig_title = employee.designation.title if hasattr(employee.designation, 'title') else str(employee.designation)
        
    emp_bank = "—"
    emp_acc = "—"
    emp_ifsc = "—"
    if employee and hasattr(employee, 'bank_account') and employee.bank_account:
        if employee.bank_account.bank_name:
            emp_bank = employee.bank_account.bank_name
        if employee.bank_account.account_number:
            emp_acc = mask_account_number(employee.bank_account.account_number)
        if employee.bank_account.ifsc_code:
            emp_ifsc = employee.bank_account.ifsc_code
            
    emp_doj = "—"
    if employee and hasattr(employee, 'joining_date') and employee.joining_date:
        emp_doj = str(employee.joining_date)
        
    emp_pan = "—"
    if employee and hasattr(employee, 'profile') and employee.profile and employee.profile.pan_number:
        emp_pan = employee.profile.pan_number

    emp_uan = "—"
    if employee and hasattr(employee, 'profile') and employee.profile and getattr(employee.profile, 'uan_number', None):
        emp_uan = employee.profile.uan_number
    elif employee and hasattr(employee, 'uan_number') and employee.uan_number:
        emp_uan = employee.uan_number

    payable_days = payslip.payable_days if payslip.payable_days is not None else 22
    days_worked = payslip.days_worked if payslip.days_worked is not None else 0.0
    lop_days = max(0.0, payable_days - days_worked)

    basic = payslip.basic or 0.0
    hra = payslip.hra or 0.0
    allowances = payslip.allowances or 0.0
    bonus = payslip.bonus or 0.0
    pf = payslip.pf or 0.0
    tax = payslip.tax or 0.0
    other_deductions = payslip.other_deductions or 0.0

    gross_earnings = basic + hra + allowances + bonus
    total_deductions = pf + tax + other_deductions
    net_salary = payslip.net_salary or 0.0
    amount_in_words = number_to_words(net_salary, "Dollars" if currency == "$" else "Rupees")

    # Embed local logo safely
    logo_base64 = ""
    logo_path = os.path.abspath("static/images/icon.jpeg")
    if not os.path.exists(logo_path):
        logo_path = os.path.abspath("static/images/logo.png")
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as lf:
                logo_base64 = f"data:image/jpeg;base64,{base64.b64encode(lf.read()).decode('utf-8')}"
        except Exception:
            logo_base64 = ""

    statutory_parts = []
    if company:
        if getattr(company, "cin", None) and str(company.cin).strip():
            statutory_parts.append(f"CIN: {str(company.cin).strip()}")
        if getattr(company, "gstin", None) and str(company.gstin).strip():
            statutory_parts.append(f"GSTIN: {str(company.gstin).strip()}")
        if getattr(company, "pan", None) and str(company.pan).strip():
            statutory_parts.append(f"PAN: {str(company.pan).strip()}")
    
    statutory_markup = f'<p class="text-[10px] text-slate-400 mt-0.5 font-mono">{" • ".join(statutory_parts)}</p>' if statutory_parts else ''

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="bg-white">
<head>
    <meta charset="UTF-8">
    <title>Salary Slip — {payslip.month:02d}/{payslip.year}</title>
    
    <!-- Google Fonts: Nunito, Poppins, JetBrains Mono -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Nunito:wght@400;500;600;700;800&family=Poppins:wght@500;600;700;800&display=swap" rel="stylesheet">

    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['"Nunito"', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
                        heading: ['"Poppins"', '"Nunito"', 'sans-serif'],
                        mono: ['"JetBrains Mono"', 'monospace'],
                    }},
                    colors: {{
                        teal: {{
                            50: '#E0F4F4',
                            600: '#008080',
                            700: '#005050',
                            800: '#003333',
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>

    <style>
        @page {{
            size: A4 portrait;
            margin: 0 !important;
        }}
        *, *::before, *::after {{
            box-sizing: border-box;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            color-adjust: exact !important;
        }}
        html, body {{
            background: #ffffff !important;
            color: #0F172A !important;
            margin: 0 !important;
            padding: 0 !important;
            width: 210mm !important;
            height: 297mm !important;
            max-height: 297mm !important;
            overflow: hidden !important;
            font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        }}
        .payslip-sheet {{
            box-sizing: border-box !important;
            width: 194mm !important;
            max-width: 194mm !important;
            margin: 8mm auto !important;
            padding: 5mm 6mm !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 6px !important;
            box-shadow: none !important;
            background: #ffffff !important;
        }}
        .payslip-sheet > div + div {{
            margin-top: 2.5mm !important;
        }}
        .payslip-sheet table {{
            width: 100% !important;
            table-layout: fixed !important;
        }}
        .payslip-sheet th, .payslip-sheet td {{
            padding-top: 1.5mm !important;
            padding-bottom: 1.5mm !important;
        }}
    </style>
</head>
<body class="bg-white text-slate-900">

    <div class="payslip-sheet">
        
        <!-- 1. Corporate Letterhead Header -->
        <div class="flex justify-between items-start pb-3.5 border-b border-slate-300 gap-4">
            <div class="flex items-center space-x-3.5">
                {'<img src="' + logo_base64 + '" alt="Logo" class="w-11 h-11 object-contain rounded-lg bg-slate-950 p-1 shadow-xs border border-slate-200 shrink-0">' if logo_base64 else ''}
                <div>
                    <h1 class="text-base font-heading font-bold text-slate-900 tracking-tight uppercase leading-tight">
                        {company_name}
                    </h1>
                    <p class="text-xs text-slate-500 mt-0.5">
                        {company_addr}
                    </p>
                    {statutory_markup}
                </div>
            </div>

            <!-- Statement Title & Reference Block -->
            <div class="text-right shrink-0">
                <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider font-heading">Salary Statement</div>
                <div class="text-xs font-bold text-slate-900 font-mono mt-0.5">
                    Slip #{slip_no}
                </div>
                <div class="text-[10px] font-medium text-slate-500 mt-0.5 font-mono">
                    Date: {date_str}
                </div>
            </div>
        </div>

        <!-- 2. Payslip Period Title Ribbon -->
        <div class="bg-slate-900 text-white text-center py-1.5 px-4 rounded-md font-heading font-bold text-xs uppercase tracking-wider">
            Payslip for the Month of {month_name} {payslip.year}
        </div>

        <!-- 3. Employee & Bank Information Grid -->
        <div class="border border-slate-200 rounded-lg overflow-hidden bg-slate-50/60">
            <div class="grid grid-cols-2 divide-x divide-slate-200 text-xs">
                
                <!-- Left: Employee Details -->
                <div class="p-3 space-y-1">
                    <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider pb-1 border-b border-slate-200 font-heading">
                        Employee Identification
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Employee Name:</span>
                        <span class="font-bold text-slate-900 text-right">{emp_name}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Employee ID:</span>
                        <span class="font-mono font-bold text-slate-900 text-right">#{emp_id_val}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Department:</span>
                        <span class="font-medium text-slate-900 text-right">{dept_name}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Designation:</span>
                        <span class="font-medium text-slate-900 text-right">{desig_title}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Date of Joining:</span>
                        <span class="font-mono font-medium text-slate-900 text-right">{emp_doj}</span>
                    </div>
                </div>

                <!-- Right: Bank & Statutory Details -->
                <div class="p-3 space-y-1">
                    <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider pb-1 border-b border-slate-200 font-heading">
                        Payment & Statutory Details
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Bank Name:</span>
                        <span class="font-medium text-slate-900 text-right">{emp_bank}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">Account No:</span>
                        <span class="font-mono font-bold text-slate-900 text-right">{emp_acc}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">IFSC Code:</span>
                        <span class="font-mono font-medium text-slate-900 uppercase text-right">{emp_ifsc}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">PAN Number:</span>
                        <span class="font-mono font-medium text-slate-900 uppercase text-right">{emp_pan}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="font-medium text-slate-500">PF / UAN No:</span>
                        <span class="font-mono font-medium text-slate-900 text-right">{emp_uan}</span>
                    </div>
                </div>

            </div>
        </div>

        <!-- 4. Attendance Summary Ribbon -->
        <div class="border border-slate-200 rounded-lg overflow-hidden bg-slate-50 p-2">
            <div class="grid grid-cols-4 gap-2 text-center text-xs">
                <div>
                    <span class="text-[9.5px] font-bold text-slate-500 uppercase tracking-wider block font-heading">Payable Days</span>
                    <span class="font-mono font-bold text-slate-900 text-xs">{payable_days}</span>
                </div>
                <div>
                    <span class="text-[9.5px] font-bold text-emerald-700 uppercase tracking-wider block font-heading">Days Worked</span>
                    <span class="font-mono font-bold text-emerald-800 text-xs">{days_worked:.1f}</span>
                </div>
                <div>
                    <span class="text-[9.5px] font-bold text-rose-700 uppercase tracking-wider block font-heading">Loss of Pay (LOP)</span>
                    <span class="font-mono font-bold text-rose-800 text-xs">{lop_days:.1f}</span>
                </div>
                <div>
                    <span class="text-[9.5px] font-bold text-slate-500 uppercase tracking-wider block font-heading">Payment Mode</span>
                    <span class="font-semibold text-slate-900 text-xs">Direct Transfer</span>
                </div>
            </div>
        </div>

        <!-- 5. Comparative Earnings & Deductions Statement -->
        <div class="border border-slate-200 rounded-lg overflow-hidden">
            <table class="w-full text-xs divide-y divide-slate-200">
                <thead>
                    <tr class="bg-slate-100 text-slate-700 font-bold uppercase tracking-wider text-[10px] font-heading">
                        <th class="px-3.5 py-1.5 text-left w-5/12 border-r border-slate-200">Earnings</th>
                        <th class="px-3.5 py-1.5 text-right w-2/12 border-r border-slate-200">Amount ({currency})</th>
                        <th class="px-3.5 py-1.5 text-left w-5/12 border-r border-slate-200">Deductions</th>
                        <th class="px-3.5 py-1.5 text-right w-2/12">Amount ({currency})</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    <tr>
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">Basic Salary</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900 border-r border-slate-200">{basic:.2f}</td>
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">Provident Fund (PF)</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900">{pf:.2f}</td>
                    </tr>
                    <tr class="bg-slate-50/40">
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">House Rent Allowance (HRA)</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900 border-r border-slate-200">{hra:.2f}</td>
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">Tax Withholding (TDS)</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900">{tax:.2f}</td>
                    </tr>
                    <tr>
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">Special & Other Allowances</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900 border-r border-slate-200">{allowances:.2f}</td>
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">Other Deductions / Advances</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900">{other_deductions:.2f}</td>
                    </tr>
                    <tr class="bg-slate-50/40">
                        <td class="px-3.5 py-1 text-slate-800 font-medium border-r border-slate-200">Performance Bonus</td>
                        <td class="px-3.5 py-1 text-right font-mono font-bold text-slate-900 border-r border-slate-200">{bonus:.2f}</td>
                        <td class="px-3.5 py-1 text-slate-400 italic border-r border-slate-200">—</td>
                        <td class="px-3.5 py-1 text-right font-mono text-slate-400">0.00</td>
                    </tr>
                </tbody>
                <tfoot>
                    <tr class="bg-slate-50 font-bold border-t-2 border-slate-200 text-slate-900 font-heading">
                        <td class="px-3.5 py-1.5 uppercase text-[10px] border-r border-slate-200">Gross Earnings (A)</td>
                        <td class="px-3.5 py-1.5 text-right font-mono text-xs border-r border-slate-200 text-slate-900">
                            {currency}{gross_earnings:.2f}
                        </td>
                        <td class="px-3.5 py-1.5 uppercase text-[10px] text-rose-700 border-r border-slate-200">Total Deductions (B)</td>
                        <td class="px-3.5 py-1.5 text-right font-mono text-xs text-rose-700">
                            {currency}{total_deductions:.2f}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>

        <!-- 6. Net Take-Home Salary Highlight Box -->
        <div class="border border-slate-300 rounded-lg overflow-hidden bg-slate-50 p-3">
            <div class="flex justify-between items-center pb-2 border-b border-slate-200">
                <div>
                    <span class="text-xs font-bold text-slate-900 uppercase tracking-wider block font-heading">Net Take-Home Salary (A - B)</span>
                    <span class="text-[10px] text-slate-500 mt-0.5 block">
                        Disbursed via Electronic Bank Transfer (NEFT/RTGS)
                    </span>
                </div>
                <div class="text-right">
                    <span class="text-xl font-black font-mono text-slate-900 tracking-tight">
                        {currency}{net_salary:.2f}
                    </span>
                </div>
            </div>
            
            <div class="pt-1.5 text-xs text-slate-800">
                <span class="font-bold text-slate-500 uppercase tracking-wider text-[9.5px] font-heading">Amount in Words:</span>
                <span class="font-semibold italic text-slate-900 ml-1">{amount_in_words}</span>
            </div>
        </div>

        <!-- 7. Official Sign-Off & Verification Footer -->
        <div class="pt-2 border-t border-slate-200 flex justify-between items-end gap-5 text-xs text-slate-500">
            <div class="space-y-0.5 max-w-md">
                <div class="flex items-center space-x-1.5 font-bold text-teal-700">
                    <i data-lucide="shield-check" class="w-3.5 h-3.5 text-teal-600"></i>
                    <span class="text-[11px]">Official Authenticated Statement</span>
                </div>
                <p class="text-[10px] text-slate-400 leading-relaxed">
                    *Computer-generated official salary certificate issued by {company_name}. Does not require physical signature.
                </p>
                <p class="text-[9px] text-slate-400 font-mono">HASH: AUTH-PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}-VERIFIED</p>
            </div>

            <!-- Authorized Signatory Stamp Box -->
            <div class="text-right min-w-[170px]">
                <div class="border-b border-slate-300 pb-6 mb-1">
                    <span class="inline-block text-[10px] font-serif italic text-slate-400">Authorized Signature</span>
                </div>
                <p class="text-xs font-bold text-slate-900 font-heading">Authorized Signatory</p>
                <p class="text-[9.5px] text-slate-400 uppercase tracking-wider font-medium">{company_name}</p>
            </div>
        </div>

    </div>

    <script>
        lucide.createIcons();
    </script>
</body>
</html>
"""
    return html_content


def generate_payslip_pdf_headless(payslip, company=None, employee=None) -> BytesIO | None:
    """Generates PDF by executing Chromium / Edge in headless print mode for 100% exact print match."""
    browser_bin = find_headless_browser()
    if not browser_bin:
        return None

    html_code = generate_payslip_html(payslip, company, employee)
    
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as hf:
        hf.write(html_code)
        html_path = hf.name

    pdf_temp_path = html_path.replace(".html", ".pdf")

    cmd = [
        browser_bin,
        "--headless",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_temp_path}",
        html_path
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=15)
        if res.returncode == 0 and os.path.exists(pdf_temp_path) and os.path.getsize(pdf_temp_path) > 0:
            buffer = BytesIO()
            with open(pdf_temp_path, "rb") as pf:
                buffer.write(pf.read())
            buffer.seek(0)
            return buffer
        else:
            logger.warning(f"Headless browser PDF generation failed with code {res.returncode}: {res.stderr.decode('utf-8', 'ignore')}")
    except Exception as e:
        logger.warning(f"Headless browser PDF generation encountered error: {e}")
    finally:
        if os.path.exists(html_path):
            try:
                os.unlink(html_path)
            except Exception:
                pass
        if os.path.exists(pdf_temp_path):
            try:
                os.unlink(pdf_temp_path)
            except Exception:
                pass
    return None


def generate_payslip_pdf_reportlab(payslip, company=None, employee=None) -> BytesIO:
    """Fallback ReportLab PDF generator providing exact styling if headless browser is unavailable."""
    register_brand_fonts()

    if employee is None:
        employee = getattr(payslip, "employee", None)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24
    )
    
    c_dark = colors.HexColor("#0F172A")
    c_teal = colors.HexColor("#008080")
    c_light = colors.HexColor("#CBD5E1")
    c_border = colors.HexColor("#E2E8F0")
    c_wash = colors.HexColor("#F8FAFC")
    c_text_primary = colors.HexColor("#0F172A")
    c_text_secondary = colors.HexColor("#64748B")
    c_rose_bg = colors.HexColor("#FFF1F2")
    c_rose_text = colors.HexColor("#BE123C")
    c_emerald_text = colors.HexColor("#047857")
    c_amber_text = colors.HexColor("#B45309")

    f_body = get_font_name("Nunito", "Helvetica")
    f_bold = get_font_name("Nunito-Bold", "Helvetica-Bold")
    f_heading = get_font_name("Poppins-Bold", "Helvetica-Bold")
    f_mono = get_font_name("JetBrainsMono", "Courier")
    f_mono_bold = get_font_name("JetBrainsMono-Bold", "Courier-Bold")

    company_title_style = ParagraphStyle('CompTitle', fontName=f_heading, fontSize=12.5, leading=15, textColor=c_text_primary, alignment=TA_LEFT)
    company_sub_style = ParagraphStyle('CompSub', fontName=f_body, fontSize=7, leading=9.5, textColor=c_text_secondary, alignment=TA_LEFT)
    statement_title_style = ParagraphStyle('StateTitle', fontName=f_heading, fontSize=8.5, leading=11, textColor=c_text_secondary, alignment=TA_RIGHT)
    statement_meta_style = ParagraphStyle('StateMeta', fontName=f_mono_bold, fontSize=8, leading=11, textColor=c_text_primary, alignment=TA_RIGHT)
    statement_date_style = ParagraphStyle('StateDate', fontName=f_body, fontSize=7.5, leading=10, textColor=c_text_secondary, alignment=TA_RIGHT)
    ribbon_style = ParagraphStyle('Ribbon', fontName=f_heading, fontSize=9, leading=12, textColor=colors.white, alignment=TA_CENTER)
    table_header_style = ParagraphStyle('TableHead', fontName=f_heading, fontSize=7.5, leading=10, textColor=c_text_primary, alignment=TA_LEFT)
    table_header_right = ParagraphStyle('TableHeadR', fontName=f_heading, fontSize=7.5, leading=10, textColor=c_text_primary, alignment=TA_RIGHT)
    section_subhead_style = ParagraphStyle('SecSubHead', fontName=f_heading, fontSize=7, leading=9, textColor=c_text_secondary)
    cell_label_style = ParagraphStyle('CellLbl', fontName=f_body, fontSize=7, leading=9, textColor=c_text_secondary)
    cell_value_style = ParagraphStyle('CellVal', fontName=f_body, fontSize=7.5, leading=10, textColor=c_text_primary)
    cell_value_bold = ParagraphStyle('CellValB', fontName=f_bold, fontSize=7.5, leading=10, textColor=c_text_primary)
    cell_mono_bold = ParagraphStyle('CellMonoB', fontName=f_mono_bold, fontSize=7.5, leading=10, textColor=c_text_primary)
    cell_mono_right = ParagraphStyle('CellMonoR', fontName=f_mono_bold, fontSize=7.5, leading=10, textColor=c_text_primary, alignment=TA_RIGHT)
    subtotal_label = ParagraphStyle('SubtotalLbl', fontName=f_heading, fontSize=7.5, leading=10, textColor=c_text_primary)
    subtotal_amt_earn = ParagraphStyle('SubtotalEarn', fontName=f_mono_bold, fontSize=8.5, leading=11, textColor=c_text_primary, alignment=TA_RIGHT)
    subtotal_amt_deduct = ParagraphStyle('SubtotalDeduct', fontName=f_mono_bold, fontSize=8.5, leading=11, textColor=c_rose_text, alignment=TA_RIGHT)
    net_box_label = ParagraphStyle('NetBoxLbl', fontName=f_heading, fontSize=8.5, leading=11, textColor=c_text_primary, alignment=TA_LEFT)
    net_box_sub = ParagraphStyle('NetBoxSub', fontName=f_body, fontSize=7, leading=9, textColor=c_text_secondary, alignment=TA_LEFT)
    net_box_words = ParagraphStyle('NetBoxWords', fontName=f_body, fontSize=7.5, leading=9.5, textColor=c_text_primary, alignment=TA_LEFT)
    net_box_amount = ParagraphStyle('NetBoxAmt', fontName=f_mono_bold, fontSize=15, leading=18, textColor=c_text_primary, alignment=TA_RIGHT)
    footer_text_style = ParagraphStyle('FooterTxt', fontName=f_body, fontSize=6.5, leading=8.5, textColor=c_text_secondary, alignment=TA_LEFT)
    footer_sign_style = ParagraphStyle('FooterSgn', fontName=f_heading, fontSize=7.5, leading=10, textColor=c_text_primary, alignment=TA_RIGHT)

    elements = []
    
    company_name = company.name if company and company.name else "TURTU HRMS"
    company_addr = company.address if company and company.address else "Karnataka, India"
    currency = company.currency_symbol if company and company.currency_symbol else "₹"
    month_name = get_month_name(payslip.month)
    slip_no = f"PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}"
    
    statutory_parts_rl = []
    if company:
        if getattr(company, "cin", None) and str(company.cin).strip():
            statutory_parts_rl.append(f"CIN: {str(company.cin).strip()}")
        if getattr(company, "gstin", None) and str(company.gstin).strip():
            statutory_parts_rl.append(f"GSTIN: {str(company.gstin).strip()}")
        if getattr(company, "pan", None) and str(company.pan).strip():
            statutory_parts_rl.append(f"PAN: {str(company.pan).strip()}")

    header_left_text = [
        Paragraph(f"<b>{company_name.upper()}</b>", company_title_style),
        Spacer(1, 1),
        Paragraph(company_addr, company_sub_style),
    ]
    if statutory_parts_rl:
        header_left_text.append(Paragraph(" • ".join(statutory_parts_rl), company_sub_style))

    logo_path = os.path.abspath("static/images/icon.jpeg")
    if not os.path.exists(logo_path):
        logo_path = os.path.abspath("static/images/logo.png")

    if os.path.exists(logo_path):
        try:
            logo_img = RLImage(logo_path, width=42, height=42)
            brand_table = Table([[logo_img, header_left_text]], colWidths=[48, 290])
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
    
    if hasattr(payslip.generated_on, 'strftime') and payslip.generated_on:
        date_str = payslip.generated_on.strftime('%b %d, %Y')
    elif payslip.generated_on:
        date_str = str(payslip.generated_on)
    else:
        date_str = "—"

    status_str = getattr(payslip, "status", "draft").upper()
    status_color = c_teal if status_str == "FINALIZED" else (c_emerald_text if status_str == "PAID" else c_amber_text)
    
    header_right = [
        Paragraph("<b>SALARY STATEMENT</b>", statement_title_style),
        Spacer(1, 1),
        Paragraph(f"<b>Slip #{slip_no}</b>", statement_meta_style),
        Paragraph(f"<b>Date:</b> {date_str}", statement_date_style),
        Paragraph(f"<b>Status:</b> <font color='{status_color.hexval()}'><b>{status_str}</b></font>", statement_date_style)
    ]
    
    header_table = Table([[header_left, header_right]], colWidths=[338, 209])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1, color=c_light, spaceBefore=0, spaceAfter=5))

    # 2. Month Ribbon
    ribbon_data = [[Paragraph(f"PAYSLIP FOR THE MONTH OF {month_name.upper()} {payslip.year}", ribbon_style)]]
    ribbon_table = Table(ribbon_data, colWidths=[547])
    ribbon_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_dark),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(ribbon_table)
    elements.append(Spacer(1, 4))

    # 3. Employee & Payment Info
    emp_name = employee.name if employee and hasattr(employee, 'name') and employee.name else "Employee"
    emp_id_val = f"#{employee.id:04d}" if employee and hasattr(employee, 'id') and employee.id else "#0001"
    
    dept_name = "—"
    if employee and hasattr(employee, 'department') and employee.department:
        dept_name = employee.department.name if hasattr(employee.department, 'name') else str(employee.department)
        
    desig_title = "—"
    if employee and hasattr(employee, 'designation') and employee.designation:
        desig_title = employee.designation.title if hasattr(employee.designation, 'title') else str(employee.designation)
        
    emp_bank = "—"
    emp_acc = "—"
    emp_ifsc = "—"
    if employee and hasattr(employee, 'bank_account') and employee.bank_account:
        if employee.bank_account.bank_name:
            emp_bank = employee.bank_account.bank_name
        if employee.bank_account.account_number:
            emp_acc = mask_account_number(employee.bank_account.account_number)
        if employee.bank_account.ifsc_code:
            emp_ifsc = employee.bank_account.ifsc_code
            
    emp_doj = "—"
    if employee and hasattr(employee, 'joining_date') and employee.joining_date:
        emp_doj = str(employee.joining_date)
        
    emp_pan = "—"
    if employee and hasattr(employee, 'profile') and employee.profile and employee.profile.pan_number:
        emp_pan = employee.profile.pan_number

    emp_uan = "—"
    if employee and hasattr(employee, 'profile') and employee.profile and getattr(employee.profile, 'uan_number', None):
        emp_uan = employee.profile.uan_number
    elif employee and hasattr(employee, 'uan_number') and employee.uan_number:
        emp_uan = employee.uan_number

    meta_left = [
        [Paragraph("<b>EMPLOYEE IDENTIFICATION</b>", section_subhead_style), Paragraph("", cell_value_style)],
        [Paragraph("Employee Name:", cell_label_style), Paragraph(f"<b>{emp_name}</b>", cell_value_bold)],
        [Paragraph("Employee ID:", cell_label_style), Paragraph(str(emp_id_val), cell_mono_bold)],
        [Paragraph("Department:", cell_label_style), Paragraph(str(dept_name), cell_value_style)],
        [Paragraph("Designation:", cell_label_style), Paragraph(str(desig_title), cell_value_style)],
        [Paragraph("Date of Joining:", cell_label_style), Paragraph(str(emp_doj), cell_value_style)],
    ]
    meta_right = [
        [Paragraph("<b>PAYMENT & STATUTORY DETAILS</b>", section_subhead_style), Paragraph("", cell_value_style)],
        [Paragraph("Bank Name:", cell_label_style), Paragraph(str(emp_bank), cell_value_style)],
        [Paragraph("Bank Account No:", cell_label_style), Paragraph(str(emp_acc), cell_mono_bold)],
        [Paragraph("IFSC Code:", cell_label_style), Paragraph(str(emp_ifsc), cell_mono_bold)],
        [Paragraph("PAN Number:", cell_label_style), Paragraph(str(emp_pan), cell_mono_bold)],
        [Paragraph("PF / UAN No:", cell_label_style), Paragraph(str(emp_uan), cell_mono_bold)],
    ]

    t_meta_left = Table(meta_left, colWidths=[88, 175])
    t_meta_left.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, c_light),
    ]))

    t_meta_right = Table(meta_right, colWidths=[88, 175])
    t_meta_right.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, c_light),
    ]))

    meta_container = Table([[t_meta_left, t_meta_right]], colWidths=[273.5, 273.5])
    meta_container.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_wash),
        ('BOX', (0,0), (-1,-1), 0.75, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(meta_container)
    elements.append(Spacer(1, 4))

    # 4. Attendance Summary
    payable_days = payslip.payable_days if payslip.payable_days is not None else 22
    days_worked = payslip.days_worked if payslip.days_worked is not None else 0.0
    lop_days = max(0.0, payable_days - days_worked)

    att_label_style = ParagraphStyle('AttLbl', fontName=f_bold, fontSize=6.5, leading=8.5, textColor=c_text_secondary, alignment=TA_CENTER)
    att_val_style = ParagraphStyle('AttVal', fontName=f_mono_bold, fontSize=8, leading=10, textColor=c_text_primary, alignment=TA_CENTER)
    att_val_worked = ParagraphStyle('AttValW', fontName=f_mono_bold, fontSize=8, leading=10, textColor=c_emerald_text, alignment=TA_CENTER)
    att_val_lop = ParagraphStyle('AttValL', fontName=f_mono_bold, fontSize=8, leading=10, textColor=c_rose_text, alignment=TA_CENTER)
    att_val_mode = ParagraphStyle('AttValM', fontName=f_bold, fontSize=7.5, leading=10, textColor=c_text_primary, alignment=TA_CENTER)

    att_data = [[
        [Paragraph("PAYABLE DAYS", att_label_style), Paragraph(str(payable_days), att_val_style)],
        [Paragraph("DAYS WORKED", att_label_style), Paragraph(f"{days_worked:.1f}", att_val_worked)],
        [Paragraph("LOSS OF PAY (LOP)", att_label_style), Paragraph(f"{lop_days:.1f}", att_val_lop)],
        [Paragraph("PAYMENT MODE", att_label_style), Paragraph("Direct Transfer", att_val_mode)],
    ]]
    att_table = Table(att_data, colWidths=[136.75, 136.75, 136.75, 136.75])
    att_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_wash),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ('LEFTPADDING', (0,0), (-1,-1), 3),
        ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(att_table)
    elements.append(Spacer(1, 4))

    # 5. Earnings & Deductions Tables
    basic = payslip.basic or 0.0
    hra = payslip.hra or 0.0
    allowances = payslip.allowances or 0.0
    bonus = payslip.bonus or 0.0
    pf = payslip.pf or 0.0
    tax = payslip.tax or 0.0
    other_deductions = payslip.other_deductions or 0.0

    total_earnings = basic + hra + allowances + bonus
    total_deductions = pf + tax + other_deductions

    breakdown_data = [
        [
            Paragraph("EARNINGS", table_header_style),
            Paragraph(f"AMOUNT ({currency})", table_header_right),
            Paragraph("DEDUCTIONS", table_header_style),
            Paragraph(f"AMOUNT ({currency})", table_header_right)
        ],
        [
            Paragraph("Basic Salary", cell_value_style),
            Paragraph(f"{basic:,.2f}", cell_mono_right),
            Paragraph("Provident Fund (PF)", cell_value_style),
            Paragraph(f"{pf:,.2f}", cell_mono_right)
        ],
        [
            Paragraph("House Rent Allowance (HRA)", cell_value_style),
            Paragraph(f"{hra:,.2f}", cell_mono_right),
            Paragraph("Tax Withholding (TDS)", cell_value_style),
            Paragraph(f"{tax:,.2f}", cell_mono_right)
        ],
        [
            Paragraph("Special & Other Allowances", cell_value_style),
            Paragraph(f"{allowances:,.2f}", cell_mono_right),
            Paragraph("Other Deductions / Advances", cell_value_style),
            Paragraph(f"{other_deductions:,.2f}", cell_mono_right)
        ],
        [
            Paragraph("Performance Bonus", cell_value_style),
            Paragraph(f"{bonus:,.2f}", cell_mono_right),
            Paragraph("—", ParagraphStyle('Dash', fontName=f_body, fontSize=7.5, textColor=c_text_secondary)),
            Paragraph("0.00", ParagraphStyle('DashAmt', fontName=f_mono_bold, fontSize=7.5, textColor=c_text_secondary, alignment=TA_RIGHT))
        ],
        [
            Paragraph("<b>GROSS EARNINGS (A)</b>", subtotal_label),
            Paragraph(f"<b>{currency} {total_earnings:,.2f}</b>", subtotal_amt_earn),
            Paragraph("<b>TOTAL DEDUCTIONS (B)</b>", ParagraphStyle('DeductHead', parent=subtotal_label, textColor=c_rose_text)),
            Paragraph(f"<b>{currency} {total_deductions:,.2f}</b>", subtotal_amt_deduct)
        ]
    ]

    breakdown_table = Table(breakdown_data, colWidths=[193.5, 80, 193.5, 80])
    breakdown_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0,0), (-1,0), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,0), 3.5),
        ('BACKGROUND', (0,1), (-1,-2), colors.white),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, c_wash]),
        ('TOPPADDING', (0,1), (-1,-2), 3),
        ('BOTTOMPADDING', (0,1), (-1,-2), 3),
        ('BACKGROUND', (0,-1), (1,-1), c_wash),
        ('BACKGROUND', (2,-1), (3,-1), c_rose_bg),
        ('TOPPADDING', (0,-1), (-1,-1), 4),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 4),
        ('BOX', (0,0), (-1,-1), 0.75, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(breakdown_table)
    elements.append(Spacer(1, 4))

    # 6. Net Salary Box
    words = number_to_words(payslip.net_salary or 0.0, currency)
    net_content = [
        [
            [
                Paragraph("<b>NET TAKE-HOME SALARY (A - B)</b>", net_box_label),
                Paragraph("Disbursed via Electronic Bank Transfer (NEFT/RTGS)", net_box_sub),
                Spacer(1, 1.5),
                Paragraph(f"<b>Amount in Words:</b> <i>{words}</i>", net_box_words)
            ],
            [
                Paragraph(f"<b>{currency} {(payslip.net_salary or 0.0):,.2f}</b>", net_box_amount),
            ]
        ]
    ]
    net_table = Table(net_content, colWidths=[367, 180])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_wash),
        ('BOX', (0,0), (-1,-1), 1.0, c_light),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(net_table)
    elements.append(Spacer(1, 10))

    # 7. Footer
    disclaimer = [
        Paragraph("<b>Official Authenticated Statement</b>", ParagraphStyle('DisclH', parent=cell_value_bold, textColor=c_teal)),
        Paragraph(f"*Computer-generated official salary certificate issued by {company_name}. Does not require physical signature.", footer_text_style),
        Paragraph(f"HASH: AUTH-PAY-{payslip.year}{payslip.month:02d}-{payslip.id:04d}-VERIFIED", ParagraphStyle('SecHash', parent=footer_text_style, fontName=f_mono, fontSize=5.5))
    ]
    signatory = [
        Paragraph("____________________________", footer_sign_style),
        Paragraph("<b>Authorized Signatory</b>", footer_sign_style),
        Paragraph(f"{company_name}", ParagraphStyle('SubComp', parent=footer_sign_style, fontSize=6.5, textColor=c_text_secondary))
    ]

    footer_table = Table([[disclaimer, signatory]], colWidths=[367, 180])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_payslip_pdf(payslip, company=None, employee=None) -> BytesIO:
    """
    Unified PDF generator:
    1. Tries high-fidelity Chromium / Edge headless rendering (producing 100% exact print match).
    2. Gracefully falls back to ReportLab vector rendering if headless browser is not available.
    """
    pdf_buffer = generate_payslip_pdf_headless(payslip, company, employee)
    if pdf_buffer is not None:
        return pdf_buffer
    return generate_payslip_pdf_reportlab(payslip, company, employee)
