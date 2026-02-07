@echo off
REM Restore database from backup
setlocal enabledelayedexpansion

set DB_HOST=localhost
set DB_PORT=5432
set DB_USER=postgres
set DB_PASSWORD=postgres
set DB_NAME=hemo_db

if "%1"=="" (
  echo.
  echo ===============================================
  echo   Database Restore Tool
  echo ===============================================
  echo.
  echo Usage: restore_db.bat [backup_file]
  echo.
  echo Example:
  echo   restore_db.bat backups\hemo_db_backup_20260207_205800.sql
  echo.
  echo Available backups:
  dir /b backups\*.sql 2>nul || echo   No backups found
  echo.
  exit /b 1
)

set BACKUP_FILE=%1

if not exist "%BACKUP_FILE%" (
  echo.
  echo ✗ Backup file not found: %BACKUP_FILE%
  echo.
  exit /b 1
)

echo.
echo ===============================================
echo   WARNING: Restoring database from backup
echo ===============================================
echo.
echo This will OVERWRITE the current database!
echo Host: %DB_HOST%
echo Database: %DB_NAME%
echo Backup file: %BACKUP_FILE%
echo.
set /p CONFIRM="Are you sure? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
  echo Cancelled.
  exit /b 0
)

echo.
echo Restoring database...
echo.

set PGPASSWORD=%DB_PASSWORD%

"C:\Program Files\PostgreSQL\17\bin\psql.exe" ^
  --host=%DB_HOST% ^
  --port=%DB_PORT% ^
  --username=%DB_USER% ^
  --dbname=%DB_NAME% ^
  --file="%BACKUP_FILE%"

if %ERRORLEVEL% == 0 (
  echo.
  echo ✓ Database restored successfully!
  echo.
) else (
  echo.
  echo ✗ Error restoring database (exit code: %ERRORLEVEL%)
  exit /b 1
)
