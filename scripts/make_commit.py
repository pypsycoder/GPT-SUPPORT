#!/usr/bin/env python3
"""
Создать коммит для миграций, обходя проблемы с lock файлом
"""
import os
import subprocess
import time
import sys
from pathlib import Path

def remove_lock():
    """Удалить lock файл"""
    lock_path = Path("d:\PROJECT\GPT-SUPPORT\.git\index.lock")
    if lock_path.exists():
        try:
            lock_path.unlink()
            print("[OK] Lock файл удалён")
            time.sleep(0.5)
        except Exception as e:
            print(f"[ERR] Не удалось удалить lock: {e}")
            return False
    return True

def main():
    os.chdir("d:\PROJECT\GPT-SUPPORT")
    
    # Удаляем lock
    if not remove_lock():
        sys.exit(1)
    
    # Пытаемся создать коммит
    result = subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "fix: resolve alembic migration heads conflict and reduce logging duplication"
        ],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    if result.returncode == 0:
        print("\n[SUCCESS] Коммит создан!")
        # Показываем созданный коммит
        result = subprocess.run(["git", "log", "-1", "--oneline"], capture_output=True, text=True)
        print("Коммит:", result.stdout)
    else:
        print(f"\n[ERROR] Коммит не создан (код {result.returncode})")
        sys.exit(1)

if __name__ == "__main__":
    main()
