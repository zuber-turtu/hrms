-- ==============================================================================
-- HRMS Database Migration: 003_snapshot_payslip_bank_details.sql
-- Target: MySQL 8.0+ / MariaDB / Amazon RDS / Google Cloud SQL
-- Safe & Idempotent (Checks schema definitions)
-- ==============================================================================

DROP PROCEDURE IF EXISTS AddColumnIfMissing;
DELIMITER //
CREATE PROCEDURE AddColumnIfMissing(
    IN tblName VARCHAR(100),
    IN colName VARCHAR(100),
    IN colDef VARCHAR(255)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = tblName 
        AND COLUMN_NAME = colName
    ) THEN
        SET @sql = CONCAT('ALTER TABLE `', tblName, '` ADD COLUMN `', colName, '` ', colDef);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

-- Add bank snapshot columns to payslips
CALL AddColumnIfMissing('payslips', 'bank_name', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('payslips', 'account_number', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('payslips', 'ifsc_code', 'VARCHAR(100) NULL');

-- Clean up helper procedure
DROP PROCEDURE IF EXISTS AddColumnIfMissing;

-- Backfill existing finalized and paid payslips from active employee_bank_accounts
UPDATE payslips p
JOIN employee_bank_accounts b ON p.employee_id = b.employee_id
SET p.bank_name = b.bank_name,
    p.account_number = b.account_number,
    p.ifsc_code = b.ifsc_code
WHERE p.status IN ('finalized', 'paid') 
  AND (p.bank_name IS NULL OR p.account_number IS NULL);

-- Record migration in tracking table
INSERT IGNORE INTO schema_migrations (version, name, applied_at) 
VALUES ('003', '003_snapshot_payslip_bank_details', UTC_TIMESTAMP());
