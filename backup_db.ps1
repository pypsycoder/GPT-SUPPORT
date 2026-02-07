#!/usr/bin/env powershell
# Скрипт для создания резервной копии БД перед миграцией

param(
    [string]$DbHost = "localhost",
    [int]$DbPort = 5432,
    [string]$DbUser = "postgres",
    [string]$DbPassword = "postgres",
    [string]$DbName = "hemo_db",
    [string]$BackupDir = "backups"
)

# Создаём папку для резервных копий
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

# Генерируем имя файла с меткой времени
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = Join-Path $BackupDir "hemo_db_backup_${timestamp}.sql"

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  Создание резервной копии БД" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Хост: $DbHost"
Write-Host "Порт: $DbPort"
Write-Host "БД: $DbName"
Write-Host "Файл: $backupFile"
Write-Host ""

# Устанавливаем переменные окружения для pg_dump
$env:PGPASSWORD = $DbPassword

try {
    # Выполняем pg_dump
    $pgDumpPath = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
    
    if (-not (Test-Path $pgDumpPath)) {
        $pgDumpPath = "pg_dump"
    }
    
    Write-Host "Выполняется резервное копирование..." -ForegroundColor Yellow
    Write-Host ""
    
    & $pgDumpPath --host=$DbHost --port=$DbPort --username=$DbUser --verbose --clean --if-exists --format=plain $DbName | Out-File -FilePath $backupFile -Encoding UTF8
    
    if ($LASTEXITCODE -eq 0) {
        $fileSize = (Get-Item $backupFile).Length / 1MB
        Write-Host ""
        Write-Host "✓ Резервная копия успешно создана!" -ForegroundColor Green
        Write-Host "  Файл: $backupFile"
        Write-Host "  Размер: $([Math]::Round($fileSize, 2)) МБ"
        Write-Host ""
        Write-Host "Восстановление из резервной копии (если понадобится):" -ForegroundColor Yellow
        Write-Host "  psql -h $DbHost -U $DbUser -d $DbName < `"$backupFile`""
        Write-Host ""
    } else {
        Write-Host "✗ Ошибка при создании резервной копии" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Ошибка: $_" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item env:PGPASSWORD -ErrorAction SilentlyContinue
}
