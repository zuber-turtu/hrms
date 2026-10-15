-- ==============================================================================
-- HRMS Database Migration: 002_company_zones_and_settings.sql
-- Target: MySQL 8.0+ / MariaDB / Amazon RDS / Google Cloud SQL
-- Safe & Idempotent (Checks schema definitions)
-- ==============================================================================

-- 1. Create company_zones table if not exists
CREATE TABLE IF NOT EXISTS company_zones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    code VARCHAR(100) NOT NULL UNIQUE,
    description TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_company_zones_name (name),
    INDEX idx_company_zones_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Create office_locations table if not exists
CREATE TABLE IF NOT EXISTS office_locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NULL,
    address TEXT NULL,
    latitude DOUBLE NOT NULL,
    longitude DOUBLE NOT NULL,
    radius_meters INT DEFAULT 200,
    is_primary BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    INDEX idx_office_locations_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Stored procedure to safely add column in MySQL if it doesn't already exist
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

-- Company Columns
CALL AddColumnIfMissing('company', 'tagline', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('company', 'currency_code', "VARCHAR(10) DEFAULT 'INR'");
CALL AddColumnIfMissing('company', 'support_email', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('company', 'website', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('company', 'standard_hours_per_day', 'FLOAT DEFAULT 8.0');
CALL AddColumnIfMissing('company', 'half_day_threshold_hours', 'FLOAT DEFAULT 4.5');
CALL AddColumnIfMissing('company', 'lunch_break_hours', 'FLOAT DEFAULT 1.0');
CALL AddColumnIfMissing('company', 'lunch_start_time', "VARCHAR(20) DEFAULT '13:00'");
CALL AddColumnIfMissing('company', 'lunch_end_time', "VARCHAR(20) DEFAULT '14:00'");
CALL AddColumnIfMissing('company', 'cin', 'VARCHAR(100) NULL');
CALL AddColumnIfMissing('company', 'gstin', 'VARCHAR(100) NULL');
CALL AddColumnIfMissing('company', 'pan', 'VARCHAR(100) NULL');
CALL AddColumnIfMissing('company', 'logo_url', 'VARCHAR(500) NULL');
CALL AddColumnIfMissing('company', 'logo_file_id', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('company', 'signature_url', 'VARCHAR(500) NULL');
CALL AddColumnIfMissing('company', 'signature_file_id', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('company', 'office_latitude', 'DOUBLE NULL');
CALL AddColumnIfMissing('company', 'office_longitude', 'DOUBLE NULL');
CALL AddColumnIfMissing('company', 'geofence_radius_meters', 'INT DEFAULT 200');
CALL AddColumnIfMissing('company', 'geofence_enabled', 'BOOLEAN DEFAULT TRUE');
CALL AddColumnIfMissing('company', 'geofence_strict_mode', 'BOOLEAN DEFAULT TRUE');
CALL AddColumnIfMissing('company', 'role_permissions', 'LONGTEXT NULL');
CALL AddColumnIfMissing('company', 'employee_id_prefix', "VARCHAR(50) DEFAULT 'TU'");
CALL AddColumnIfMissing('company', 'employee_id_separator', "VARCHAR(10) DEFAULT '-'");
CALL AddColumnIfMissing('company', 'employee_id_include_year', 'BOOLEAN DEFAULT TRUE');
CALL AddColumnIfMissing('company', 'employee_id_include_dept', 'BOOLEAN DEFAULT TRUE');
CALL AddColumnIfMissing('company', 'employee_id_padding', 'INT DEFAULT 3');

-- Employee Columns
CALL AddColumnIfMissing('employees', 'zone_id', 'INT NULL');
CALL AddColumnIfMissing('employees', 'hr_zone_scope', "VARCHAR(50) DEFAULT 'all'");
CALL AddColumnIfMissing('employees', 'personal_email', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('employees', 'company_email', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('employees', 'token_version', 'INT DEFAULT 1');

-- Employee Profiles Columns
CALL AddColumnIfMissing('employee_profiles', 'lunch_break_hours', 'FLOAT DEFAULT 1.0');
CALL AddColumnIfMissing('employee_profiles', 'lunch_start_time', "VARCHAR(20) DEFAULT '13:00'");
CALL AddColumnIfMissing('employee_profiles', 'lunch_end_time', "VARCHAR(20) DEFAULT '14:00'");
CALL AddColumnIfMissing('employee_profiles', 'is_geofence_exempt', 'BOOLEAN DEFAULT FALSE');

-- Attendance Columns
CALL AddColumnIfMissing('attendance', 'check_in_lat', 'DOUBLE NULL');
CALL AddColumnIfMissing('attendance', 'check_in_lon', 'DOUBLE NULL');
CALL AddColumnIfMissing('attendance', 'check_in_distance_m', 'FLOAT NULL');
CALL AddColumnIfMissing('attendance', 'check_in_in_range', 'BOOLEAN DEFAULT FALSE');
CALL AddColumnIfMissing('attendance', 'check_in_location_name', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('attendance', 'check_out_lat', 'DOUBLE NULL');
CALL AddColumnIfMissing('attendance', 'check_out_lon', 'DOUBLE NULL');
CALL AddColumnIfMissing('attendance', 'check_out_distance_m', 'FLOAT NULL');
CALL AddColumnIfMissing('attendance', 'check_out_in_range', 'BOOLEAN DEFAULT FALSE');
CALL AddColumnIfMissing('attendance', 'check_out_location_name', 'VARCHAR(255) NULL');
CALL AddColumnIfMissing('attendance', 'work_mode', "VARCHAR(50) DEFAULT 'office'");
CALL AddColumnIfMissing('attendance', 'wfh_request_id', 'INT NULL');
CALL AddColumnIfMissing('attendance', 'is_overridden', 'BOOLEAN DEFAULT FALSE');
CALL AddColumnIfMissing('attendance', 'override_reason', 'VARCHAR(500) NULL');

-- Clean up helper procedure
DROP PROCEDURE IF EXISTS AddColumnIfMissing;

-- Record migration in tracking table if tracking table exists
INSERT IGNORE INTO schema_migrations (version, name, applied_at) 
VALUES ('002', '002_company_zones_and_settings', UTC_TIMESTAMP());
