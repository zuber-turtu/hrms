import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime

from app.config import settings
from app.templates_config import get_global_company

logger = logging.getLogger("uvicorn.error")


def _get_base_styles() -> str:
    """Returns the unified premium email styling."""
    return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f7f7;
            margin: 0;
            padding: 24px;
            color: #1c2b2b;
        }
        .container {
            max-width: 540px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 16px;
            border: 1px solid #b3e3e3;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }
        .header {
            background-color: #002626;
            padding: 24px;
            text-align: center;
        }
        .header h1 {
            color: #ffffff;
            font-size: 20px;
            margin: 0;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .header p {
            color: #80c7c7;
            font-size: 11px;
            margin: 4px 0 0 0;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
        }
        .content {
            padding: 32px 28px;
        }
        .greeting {
            font-size: 16px;
            font-weight: 700;
            color: #1c2b2b;
            margin-bottom: 12px;
        }
        .message {
            font-size: 14px;
            line-height: 1.6;
            color: #4a5568;
            margin-bottom: 20px;
        }
        .credentials-box {
            background-color: #f0fdfa;
            border: 1px solid #99f6e4;
            border-radius: 10px;
            padding: 16px 20px;
            margin: 20px 0;
        }
        .cred-row {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 13px;
        }
        .cred-label {
            color: #0f766e;
            font-weight: 600;
        }
        .cred-val {
            font-family: monospace;
            font-weight: 700;
            color: #115e59;
            background: #ccfbf1;
            padding: 2px 8px;
            border-radius: 4px;
        }
        .button-wrapper {
            text-align: center;
            margin: 28px 0;
        }
        .btn {
            display: inline-block;
            background-color: #008080;
            color: #ffffff !important;
            text-decoration: none;
            padding: 13px 32px;
            font-size: 14px;
            font-weight: 700;
            border-radius: 10px;
            letter-spacing: 0.3px;
        }
        .link-fallback {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px;
            font-size: 11px;
            color: #64748b;
            word-break: break-all;
            margin-top: 20px;
        }
        .link-fallback a {
            color: #008080;
            text-decoration: none;
        }
        .footer {
            padding: 20px 28px;
            background-color: #f8fafc;
            border-top: 1px solid #e2e8f0;
            font-size: 12px;
            color: #718096;
            line-height: 1.5;
        }
        .footer-note {
            font-size: 11px;
            color: #a0aec0;
            margin-top: 10px;
        }
    """


def send_smtp_email(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str,
    company=None,
) -> bool:
    """
    Core SMTP email sender supporting Google SMTP, standard SMTP, and dev mode console logging.
    """
    if not company:
        company = get_global_company()

    company_name = company.name if company and company.name else settings.COMPANY_NAME

    # Development / Fallback mode when SMTP credentials are not set
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        separator = "=" * 70
        logger.info(
            f"\n{separator}\n"
            f"[SMTP DEV MODE] Email To: {to_email}\n"
            f"Subject: {subject}\n"
            f"Content:\n{text_content}\n"
            f"{separator}\n"
        )
        print(
            f"\n{separator}\n"
            f"[SMTP DEV MODE] Email To: {to_email}\n"
            f"Subject: {subject}\n"
            f"Content:\n{text_content}\n"
            f"{separator}\n",
            flush=True,
        )
        return True

    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    from_name = settings.SMTP_FROM_NAME or company_name

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
            if settings.SMTP_USE_TLS:
                server.starttls()

        smtp_user = settings.SMTP_USER.strip() if settings.SMTP_USER else ""
        smtp_pass = settings.SMTP_PASSWORD.strip() if settings.SMTP_PASSWORD else ""
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()

        logger.info(f"Email '{subject}' sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email '{subject}' to {to_email}: {str(e)}")
        print(f"[SMTP Error] Failed to send email to {to_email}: {str(e)}", flush=True)
        return False


def send_password_reset_email(
    to_email: str,
    recipient_name: str,
    reset_url: str,
    company=None,
) -> bool:
    """Sends a password reset verification link email."""
    if not company:
        company = get_global_company()
    company_name = company.name if company and company.name else settings.COMPANY_NAME
    expire_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    subject = f"Password Reset Request — {company_name}"

    text_content = (
        f"Hello {recipient_name},\n\n"
        f"We received a request to reset your password for {company_name}.\n\n"
        f"Click the link below or copy it into your browser to reset your password:\n"
        f"{reset_url}\n\n"
        f"This link is valid for {expire_minutes} minutes.\n\n"
        f"If you did not request this, please ignore this email.\n"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
    <style>{_get_base_styles()}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{company_name}</h1>
            <p>Security & Access Control</p>
        </div>
        <div class="content">
            <div class="greeting">Hello {recipient_name},</div>
            <div class="message">
                We received a request to reset the password for your <strong>{company_name}</strong> account. Click the button below to choose a new password:
            </div>
            
            <div class="button-wrapper">
                <a href="{reset_url}" class="btn" target="_blank">Reset My Password</a>
            </div>
            
            <div class="message" style="font-size: 13px; color: #718096; margin-bottom: 0;">
                ⏱ <em>This link is valid for <strong>{expire_minutes} minutes</strong> and can only be used once.</em>
            </div>

            <div class="link-fallback">
                If the button above does not work, copy and paste this link into your browser:<br>
                <a href="{reset_url}">{reset_url}</a>
            </div>
        </div>
        <div class="footer">
            If you did not request a password reset, please ignore this email or contact your HR administrator immediately.<br>
            <div class="footer-note">
                © {company_name} • Automated Security Notification
            </div>
        </div>
    </div>
</body>
</html>"""

    return send_smtp_email(to_email, subject, text_content, html_content, company=company)


def send_admin_password_reset_email(
    to_email: str,
    recipient_name: str,
    new_password: str,
    login_url: str,
    company=None,
) -> bool:
    """Sends notification to an employee when an Administrator resets their password."""
    if not company:
        company = get_global_company()
    company_name = company.name if company and company.name else settings.COMPANY_NAME
    subject = f"Your Password Has Been Reset — {company_name}"

    text_content = (
        f"Hello {recipient_name},\n\n"
        f"An administrator has updated your password for your {company_name} account.\n\n"
        f"Your New Login Credentials:\n"
        f"Email: {to_email}\n"
        f"Temporary Password: {new_password}\n\n"
        f"Log in here: {login_url}\n\n"
        f"We recommend changing your password after logging in.\n"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Password Reset by Administrator</title>
    <style>{_get_base_styles()}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{company_name}</h1>
            <p>Administrative Account Update</p>
        </div>
        <div class="content">
            <div class="greeting">Hello {recipient_name},</div>
            <div class="message">
                An administrator has reset the password for your <strong>{company_name}</strong> portal account. You can now log in using your updated credentials below:
            </div>
            
            <div class="credentials-box">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 6px 0; color: #0f766e; font-weight: 600; font-size: 13px;">Login Email:</td>
                        <td style="padding: 6px 0; text-align: right; font-weight: 700; color: #115e59; font-size: 13px;">{to_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 0; color: #0f766e; font-weight: 600; font-size: 13px;">New Password:</td>
                        <td style="padding: 6px 0; text-align: right;"><span style="background: #ccfbf1; padding: 3px 10px; border-radius: 4px; font-family: monospace; font-weight: 700; color: #0f766e;">{new_password}</span></td>
                    </tr>
                </table>
            </div>

            <div class="button-wrapper">
                <a href="{login_url}" class="btn" target="_blank">Log In to Portal</a>
            </div>

            <div class="message" style="font-size: 13px; color: #718096; margin-bottom: 0;">
                🔒 <em>For your security, please change your password after logging in under your Account Settings.</em>
            </div>
        </div>
        <div class="footer">
            If you did not authorize this change, please contact your System Administrator or HR department immediately.<br>
            <div class="footer-note">
                © {company_name} • Automated Security Notification
            </div>
        </div>
    </div>
</body>
</html>"""

    return send_smtp_email(to_email, subject, text_content, html_content, company=company)


def send_password_changed_notification_email(
    to_email: str,
    recipient_name: str,
    changed_at: Optional[str] = None,
    company=None,
) -> bool:
    """Sends a security confirmation when a user successfully updates their own password."""
    if not company:
        company = get_global_company()
    company_name = company.name if company and company.name else settings.COMPANY_NAME
    time_str = changed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Security Alert: Password Changed — {company_name}"

    text_content = (
        f"Hello {recipient_name},\n\n"
        f"The password for your {company_name} account was successfully changed on {time_str}.\n\n"
        f"If you made this change, no further action is required.\n"
        f"If you did NOT make this change, please contact your administrator immediately.\n"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Alert: Password Changed</title>
    <style>{_get_base_styles()}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{company_name}</h1>
            <p>Security Alert</p>
        </div>
        <div class="content">
            <div class="greeting">Hello {recipient_name},</div>
            <div class="message">
                This is a confirmation that the password for your <strong>{company_name}</strong> account was successfully updated on <strong>{time_str}</strong>.
            </div>
            
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 14px 18px; margin: 20px 0; color: #166534; font-size: 13px;">
                ✅ <strong>Your account is secure.</strong> If you authorized this change, you can safely ignore this notification.
            </div>

            <div class="message" style="font-size: 13px; color: #dc2626; margin-bottom: 0;">
                ⚠️ <em>If you did not perform this action, please contact your HR or IT Administrator immediately to secure your account.</em>
            </div>
        </div>
        <div class="footer">
            Automated security notification from {company_name}.<br>
            <div class="footer-note">
                © {company_name} • Security & Compliance
            </div>
        </div>
    </div>
</body>
</html>"""

    return send_smtp_email(to_email, subject, text_content, html_content, company=company)


def send_welcome_credentials_email(
    to_email: str,
    recipient_name: str,
    password: str,
    login_url: str,
    role: str = "employee",
    company=None,
) -> bool:
    """Sends onboarding welcome email with login credentials to a newly created employee."""
    if not company:
        company = get_global_company()
    company_name = company.name if company and company.name else settings.COMPANY_NAME
    subject = f"Welcome to {company_name} — Your Portal Credentials"

    text_content = (
        f"Hello {recipient_name},\n\n"
        f"Welcome to {company_name}! Your portal account has been created.\n\n"
        f"Your Login Credentials:\n"
        f"Portal URL: {login_url}\n"
        f"Login Email: {to_email}\n"
        f"Temporary Password: {password}\n\n"
        f"Role: {role.title()}\n\n"
        f"Please log in and update your password on your first sign-in.\n"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to {company_name}</title>
    <style>{_get_base_styles()}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{company_name}</h1>
            <p>Welcome to the Team</p>
        </div>
        <div class="content">
            <div class="greeting">Welcome, {recipient_name}! 🎉</div>
            <div class="message">
                Your employee portal account for <strong>{company_name}</strong> is ready. You can now access your attendance, payroll, leave requests, and company documents.
            </div>
            
            <div class="credentials-box">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 6px 0; color: #0f766e; font-weight: 600; font-size: 13px;">Login Email:</td>
                        <td style="padding: 6px 0; text-align: right; font-weight: 700; color: #115e59; font-size: 13px;">{to_email}</td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 0; color: #0f766e; font-weight: 600; font-size: 13px;">Temporary Password:</td>
                        <td style="padding: 6px 0; text-align: right;"><span style="background: #ccfbf1; padding: 3px 10px; border-radius: 4px; font-family: monospace; font-weight: 700; color: #0f766e;">{password}</span></td>
                    </tr>
                    <tr>
                        <td style="padding: 6px 0; color: #0f766e; font-weight: 600; font-size: 13px;">Assigned Role:</td>
                        <td style="padding: 6px 0; text-align: right; font-weight: 600; color: #115e59; font-size: 13px;">{role.replace('_', ' ').title()}</td>
                    </tr>
                </table>
            </div>

            <div class="button-wrapper">
                <a href="{login_url}" class="btn" target="_blank">Access Portal & Log In</a>
            </div>

            <div class="message" style="font-size: 13px; color: #718096; margin-bottom: 0;">
                💡 <em>Tip: Please change your temporary password after logging in.</em>
            </div>
        </div>
        <div class="footer">
            If you need assistance, please contact your HR administrator.<br>
            <div class="footer-note">
                © {company_name} • Personnel & Operations
            </div>
        </div>
    </div>
</body>
</html>"""

    return send_smtp_email(to_email, subject, text_content, html_content, company=company)
