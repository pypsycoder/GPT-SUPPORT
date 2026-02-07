@echo off
REM Backup database before migration
setlocal enabledelayedexpansion

set DB_HOST=localhost
set DB_PORT=5432
set DB_USER=postgres
set DB_PASSWORD=postgres
set DB_NAME=hemo_db

if not exist "backups" mkdir backups

for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c%%a%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a%%b)

set BACKUP_FILE=backups\hemo_db_backup_!mydate!_!mytime!.sql

echo.
echo ===============================================
echo   Creating database backup...
echo ===============================================
echo.
echo Host: %DB_HOST%
echo Port: %DB_PORT%
echo Database: %DB_NAME%
echo Backup file: %BACKUP_FILE%
echo.

set PGPASSWORD=%DB_PASSWORD%

"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" ^
  --host=%DB_HOST% ^
  --port=%DB_PORT% ^
  --username=%DB_USER% ^
  --verbose ^
  --clean ^
  --if-exists ^
  --format=plain ^
  %DB_NAME% > "%BACKUP_FILE%"

if %ERRORLEVEL% == 0 (
  echo.
  echo ✓ Backup created successfully!
  echo Backup file: %BACKUP_FILE%
  dir "%BACKUP_FILE%"
  echo.
  echo To restore database if migration fails:
  echo   psql -h %DB_HOST% -U %DB_USER% -d %DB_NAME% ^< "%BACKUP_FILE%"
  echo.
) else (
  echo.
  echo ✗ Error creating backup (exit code: %ERRORLEVEL%)
  exit /b 1
)
