-- =========================================================================
-- Migration 005: Ensure Super Admin Account Exists (MySQL / PostgreSQL / SQLite)
-- Safely promotes admin@hrms.local (or earliest admin) to 'super_admin'
-- if no super admin account currently exists.
-- =========================================================================

-- Step 1: Promote admin@hrms.local to super_admin if no super_admin exists
UPDATE employees
SET role = 'super_admin', name = 'Super Admin'
WHERE LOWER(email) = 'admin@hrms.local'
  AND (SELECT count_super FROM (SELECT COUNT(*) AS count_super FROM employees WHERE role = 'super_admin') AS sub) = 0;

-- Step 2: Fallback - If still no super_admin exists, elevate earliest admin
UPDATE employees
SET role = 'super_admin'
WHERE role = 'admin'
  AND (SELECT count_super FROM (SELECT COUNT(*) AS count_super FROM employees WHERE role = 'super_admin') AS sub) = 0
ORDER BY id ASC
LIMIT 1;

-- Verification Query:
SELECT id, name, email, role, is_active FROM employees WHERE role = 'super_admin';
