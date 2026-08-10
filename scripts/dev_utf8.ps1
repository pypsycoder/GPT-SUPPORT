[CmdletBinding()]
param()

$utf8 = [System.Text.UTF8Encoding]::new($false)

try {
    chcp 65001 | Out-Null
} catch {
    Write-Warning "Could not switch code page to 65001: $($_.Exception.Message)"
}

[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$env:PYTHONIOENCODING = "utf-8"

Write-Host "UTF-8 mode enabled for the current PowerShell session." -ForegroundColor Green
Write-Host "Example:" -ForegroundColor Cyan
Write-Host "  . .\scripts\dev_utf8.ps1" -ForegroundColor White
Write-Host "You can now run uvicorn / pytest / git with UTF-8 console output." -ForegroundColor White
