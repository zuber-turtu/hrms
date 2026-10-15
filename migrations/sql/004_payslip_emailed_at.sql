-- ==============================================================================
-- HRMS Database Migration: 004_payslip_emailed_at.sql
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

-- Add emailed_at timestamp column to payslips
CALL AddColumnIfMissing('payslips', 'emailed_at', 'DATETIME NULL');

-- Clean up helper procedure
DROP PROCEDURE IF EXISTS AddColumnIfMissing;

-- Record migration in tracking table
INSERT IGNORE INTO schema_migrations (version, name, applied_at) 
VALUES ('004', '004_payslip_emailed_at', UTC_TIMESTAMP());
