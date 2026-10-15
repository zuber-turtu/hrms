# HRMS Automated Email Notifications Reference Guide

This document outlines all scenarios, events, and triggers where automated emails are dispatched to users in the **Turtu HRMS** platform.

---

## Quick Reference Summary Table

| # | Category | Trigger Event | Recipient | Subject Line | Function in Code |
|:---:|:---|:---|:---|:---|:---|
| **1** | **Onboarding** | New employee created by Admin/HR | Newly Created Employee | `Welcome to {Company} — Your Portal Credentials` | [`send_welcome_credentials_email`](#1-employee-onboarding--welcome-credentials) |
| **2** | **Security** | Employee requests password reset | Requesting User | `Password Reset Request — {Company}` | [`send_password_reset_email`](#2-self-service-password-reset-request-link) |
| **3** | **Security** | Admin triggers reset link from employee profile | Target Employee | `Password Reset Request — {Company}` | [`send_password_reset_email`](#3-admin-triggered-password-reset-link) |
| **4** | **Security** | Admin directly sets a new temporary password | Target Employee | `Your Password Has Been Reset — {Company}` | [`send_admin_password_reset_email`](#4-admin-direct-password-reset) |
| **5** | **Security** | User changes own password in settings | Account Owner | `Security Alert: Password Changed — {Company}` | [`send_password_changed_notification_email`](#5-password-changed-security-alert) |
| **6** | **Security** | User completes reset via email token link | Account Owner | `Security Alert: Password Changed — {Company}` | [`send_password_changed_notification_email`](#5-password-changed-security-alert) |
| **7** | **Leaves** | Employee submits leave application | Applicant | `Leave Request APPLIED — {Type} ({Company})` | [`send_leave_status_email`](#6-leave-application-submitted) |
| **8** | **Leaves** | Manager/HR/Admin approves leave | Applicant | `Leave Request APPROVED — {Type} ({Company})` | [`send_leave_status_email`](#7-leave-application-approved) |
| **9** | **Leaves** | Manager/HR/Admin declines leave | Applicant | `Leave Request REJECTED — {Type} ({Company})` | [`send_leave_status_email`](#8-leave-application-rejected) |
| **10** | **Leaves** | Admin grants bulk/team leave days | Each Targeted Employee | `Leave Request APPROVED — {Type} ({Company})` | [`send_leave_status_email`](#9-bulk--team-leave-grant) |
| **11** | **Remote / WFH** | Manager/HR approves WFH request | Applicant | `Work From Home (WFH) Request APPROVED — {Company}` | [`send_wfh_status_email`](#10-work-from-home-wfh-approved) |
| **12** | **Remote / WFH** | Manager/HR declines WFH request | Applicant | `Work From Home (WFH) Request REJECTED — {Company}` | [`send_wfh_status_email`](#11-work-from-home-wfh-rejected) |
| **13** | **Remote / WFH** | Manager/Admin bulk-allocates WFH days | Each Targeted Employee | `Work From Home (WFH) Request ALLOCATED — {Company}` | [`send_wfh_status_email`](#12-work-from-home-wfh-allocated) |
| **14** | **Payroll** | Admin/HR dispatches payslip (Single, Selected, or Department/Batch) | Each Targeted Employee | `Official Salary Payslip — {Month} {Year} ({Company})` | [`send_payslip_email`](#13-payroll-salary-statement--payslip-pdf-email) |

---

## Detailed Email Triggers & Specifications

### 1. Employee Onboarding & Welcome Credentials

* **Trigger Event:** When an Administrator or HR creates a new employee profile in the portal.
* **Initiated From:**
  * Web UI: `POST /employees/create`
  * REST API: `POST /api/v1/employees/`
* **Recipient:** The newly added employee (`emp.email`).
* **Subject:** `Welcome to {Company Name} — Your Portal Credentials`
* **Sender Function:** `send_welcome_credentials_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Welcome greeting and company branding.
  * Portal login URL (`APP_BASE_URL/login`).
  * **Login Email address**.
  * **Temporary/Generated Password**.
  * Assigned role (`Super Admin`, `Admin`, `HR`, `Manager`, `Employee`, `Intern`).
  * Recommendation to update temporary password upon initial sign-in.

---

### 2. Self-Service Password Reset Request Link

* **Trigger Event:** When an employee clicks "Forgot Password?" on the login screen and submits their registered email address.
* **Initiated From:**
  * Web UI: `POST /forgot-password`
* **Recipient:** The employee associated with the email address (`user.email`).
* **Subject:** `Password Reset Request — {Company Name}`
* **Sender Function:** `send_password_reset_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Single-use cryptographically secure reset button/link (`/reset-password?token={token}`).
  * Token expiration notice (**30 minutes**).
  * Warning stating that if they did not request the reset, they can safely ignore the email.

---

### 3. Admin-Triggered Password Reset Link

* **Trigger Event:** When an Administrator or HR visits an employee's profile view and chooses the **"Send Password Reset Verification Link"** action.
* **Initiated From:**
  * Web UI: `POST /employees/{emp_id}/reset-password` (with `reset_mode="email_link"`)
* **Recipient:** Target employee (`employee.email`).
* **Subject:** `Password Reset Request — {Company Name}`
* **Sender Function:** `send_password_reset_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Single-use reset link valid for 30 minutes.
  * Direct action button to set a new password.

---

### 4. Admin Direct Password Reset

* **Trigger Event:** When an Administrator directly overrides an employee's password by typing a new temporary password in the Admin panel.
* **Initiated From:**
  * Web UI: `POST /employees/{emp_id}/reset-password` (with `reset_mode="direct"`)
  * REST API: `POST /api/v1/employees/{emp_id}/reset-password`
* **Recipient:** Target employee (`employee.email`).
* **Subject:** `Your Password Has Been Reset — {Company Name}`
* **Sender Function:** `send_admin_password_reset_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Notice that an administrator reset their portal password.
  * Registered **Login Email**.
  * The **New Password** entered by the administrator.
  * Button linking directly to the portal login page.
  * Security advisory to change password under Account Settings.

---

### 5. Password Changed Security Alert

* **Trigger Event:** 
  1. An employee updates their own password inside the portal (`/change-password`).
  2. An employee completes a password reset using the tokenized link (`/reset-password`).
* **Initiated From:**
  * Web UI: `POST /change-password`
  * Web UI: `POST /reset-password`
  * REST API: `POST /api/v1/auth/change-password`
* **Recipient:** The account owner (`current_user.email`).
* **Subject:** `Security Alert: Password Changed — {Company Name}`
* **Sender Function:** `send_password_changed_notification_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Confirmation timestamp in IST (e.g., `2026-10-13 08:35 AM IST`).
  * Confirmation that the password was updated successfully.
  * Warning: If they did *not* authorize this change, to immediately contact HR or IT administrators.

---

### 6. Leave Application Submitted

* **Trigger Event:** When an employee applies for time-off.
* **Initiated From:**
  * Web UI: `POST /leaves/apply`
  * REST API: `POST /api/v1/leaves/apply`
* **Recipient:** The applying employee (`current_user.email`).
* **Subject:** `Leave Request APPLIED — {Leave Type Name} ({Company Name})`
* **Sender Function:** `send_leave_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status badge: **APPLIED**.
  * Leave Category (e.g., Casual Leave, Sick Leave, Paid Leave).
  * Date range and duration (e.g., `2026-10-15 to 2026-10-17 (3.0 day(s))`).
  * Reason submitted by the employee.
  * Button linking to the Leave Portal.

---

### 7. Leave Application Approved

* **Trigger Event:** When a Manager, HR, or Super Admin reviews and approves an employee's leave request.
* **Initiated From:**
  * Web UI: `POST /leaves/{application_id}/approve`
  * REST API: `POST /api/v1/leaves/{application_id}/review` (with `status="approved"`)
* **Recipient:** The applicant employee (`app.employee.email`).
* **Subject:** `Leave Request APPROVED — {Leave Type Name} ({Company Name})`
* **Sender Function:** `send_leave_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status badge: **APPROVED**.
  * Approved dates and duration.
  * Leave category name and stated reason.
  * Button linking to the Leave Portal.

---

### 8. Leave Application Rejected

* **Trigger Event:** When a Manager, HR, or Super Admin reviews and declines an employee's leave request.
* **Initiated From:**
  * Web UI: `POST /leaves/{application_id}/reject`
  * REST API: `POST /api/v1/leaves/{application_id}/review` (with `status="rejected"`)
* **Recipient:** The applicant employee (`app.employee.email`).
* **Subject:** `Leave Request REJECTED — {Leave Type Name} ({Company Name})`
* **Sender Function:** `send_leave_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status badge: **REJECTED**.
  * Reason for rejection (**Reviewer Remarks** provided by manager/HR).
  * Details of requested dates and category.

---

### 9. Bulk / Team Leave Grant

* **Trigger Event:** When an Administrator or HR directly grants leaves to a department, team, or specific employees via the Bulk Allocation Center.
* **Initiated From:**
  * Web UI: `POST /leaves/bulk-grant` (with `send_email=true`)
* **Recipient:** Every affected employee in the selected scope (`emp.email`).
* **Subject:** `Leave Request APPROVED — {Leave Type Name} ({Company Name})`
* **Sender Function:** `send_leave_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status: **APPROVED**.
  * Granted dates and duration.
  * Remarks: `Granted by {Admin Name}`.
  * Notes on quota deduction or statutory holiday coverage.

---

### 10. Work From Home (WFH) Approved

* **Trigger Event:** When an authorized reviewer approves an employee's WFH request.
* **Initiated From:**
  * Web UI: `POST /leaves/wfh/{request_id}/approve`
* **Recipient:** The employee who requested remote work (`wfh.employee.email`).
* **Subject:** `Work From Home (WFH) Request APPROVED — {Company Name}`
* **Sender Function:** `send_wfh_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status: **APPROVED**.
  * Approved dates and duration.
  * **Remote Punch Notice:** Explains that on approved WFH dates, **office geofence validation is bypassed**, allowing the employee to check in/out from home.
  * Direct link to the Attendance Portal.

---

### 11. Work From Home (WFH) Rejected

* **Trigger Event:** When an authorized reviewer declines an employee's WFH request.
* **Initiated From:**
  * Web UI: `POST /leaves/wfh/{request_id}/reject`
* **Recipient:** The employee who requested remote work (`wfh.employee.email`).
* **Subject:** `Work From Home (WFH) Request REJECTED — {Company Name}`
* **Sender Function:** `send_wfh_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status: **REJECTED**.
  * Rejection remarks provided by the reviewer.
  * Dates requested and reason.

---

### 12. Work From Home (WFH) Allocated

* **Trigger Event:** When a Manager or Admin directly assigns WFH days to an employee or team without requiring a prior application.
* **Initiated From:**
  * Web UI: `POST /leaves/wfh/allocate` (with `send_email=true`)
  * REST API: `POST /api/v1/leaves/wfh/allocate`
* **Recipient:** Every employee allocated remote working days (`emp.email`).
* **Subject:** `Work From Home (WFH) Request ALLOCATED — {Company Name}`
* **Sender Function:** `send_wfh_status_email()` in `app/services/email_service.py`
* **Email Contents:**
  * Status: **ALLOCATED**.
  * Allocated WFH dates and duration.
  * Reviewer remarks: `Allocated by {Manager/Admin Name}`.
  * Confirmation that remote punch is enabled for the assigned dates.

---

### 13. Payroll Salary Statement & Payslip PDF Email

* **Trigger Event:** When an Administrator or HR user sends payslips to employees (available via individual payslip action, multi-select bulk toolbar, or department/workforce bulk dispatch modal).
* **Eligibility Rule:** **Strictly Finalized or Paid payslips only.** Draft payslips are protected and excluded from dispatch.
* **Initiated From:**
  * Web UI (Single): `POST /payroll/{id}/send-email`
  * Web UI (Selected Batch): `POST /payroll/bulk-send-email`
  * Web UI (Department / Period): `POST /payroll/department-send-email`
* **Recipient:** The employee associated with the payslip (`emp.email`).
* **Subject:** `Official Salary Payslip — {Month Name} {Year} ({Company Name})`
* **Sender Function:** `send_payslip_email()` in `app/services/email_service.py`
* **Email Contents & Attachments:**
  * Employee name and corporate greeting.
  * Pay period (`Month Year`).
  * **Net Payable Salary** (formatted with company currency symbol).
  * **Disbursement Status** (`FINALIZED` or `PAID`).
  * Payable days vs worked days.
  * Bank account snapshot (Bank name + masked account number).
  * **Attached Official PDF Payslip:** Vector/High-fidelity PDF statement (`Payslip_{Name}_{Month}_{Year}.pdf`) attached directly to the message.
  * Direct action link: `APP_BASE_URL/payroll/{id}/view`.
* **Audit & State Tracking:**
  * Sets `payslip.emailed_at` timestamp.
  * Creates `AuditLog` entry with action `PAYSLIP_EMAIL_SENT`.
  * Renders `✉️ Emailed` badge on payroll table with timestamp tooltip.

---

## Technical Delivery Details

### Non-Blocking Asynchronous Background Tasks
All emails are queued via FastAPI's `BackgroundTasks.add_task()`. This means:
* HTTP requests return immediately without freezing the user's browser.
* Network latency with the SMTP mail server does not impact page responsiveness.

### SMTP & Fallback Behavior
1. **Production Mode (SMTP Active):** When `SMTP_HOST` and `SMTP_USER` are defined in `.env`, the system establishes an SSL or STARTTLS connection to send multipart MIME emails (both clean plain-text and responsive HTML).
2. **Development / Fallback Mode:** If SMTP credentials are empty or missing, emails are automatically logged cleanly to the server console/logs for testing without throwing errors.
