@echo off
cd /d "d:\PROJECT\GPT-SUPPORT"

REM Kill all git processes
taskkill /F /IM git.exe 2>nul
timeout /t 2 /nobreak

REM Clean up lock files
del ".git\index.lock" 2>nul
del ".git\config.lock" 2>nul

REM Try to add and commit in a loop
setlocal enabledelayedexpansion
for /L %%i in (1,1,10) do (
    del ".git\index.lock" 2>nul
    git add alembic.ini alembic/env.py alembic/versions/d2f20e5011be_merge_multiple_heads.py scripts/check_heads.py 2>nul
    if !errorlevel! equ 0 (
        del ".git\index.lock" 2>nul
        timeout /t 1 /nobreak
        git commit -m "fix: resolve alembic migration heads conflict and reduce logging duplication"
        if !errorlevel! equ 0 (
            echo SUCCESS: Commit created!
            git log -1 --oneline
            exit /b 0
        )
    )
    timeout /t 1 /nobreak
)

echo FAILED: Could not create commit after 10 attempts
exit /b 1
