"""
Change researcher password interactively.

Usage:
    python -m scripts.change_researcher_password

Run from the project root directory (GPT-SUPPORT/).
"""

import asyncio
import getpass
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.auth.security import hash_password  # noqa: E402
from core.db.session import async_session_factory  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id, username, full_name FROM users.researchers ORDER BY id")
        )
        researchers = result.fetchall()

        if not researchers:
            print("Нет ни одного исследователя в базе данных.")
            return

        print("\nСписок исследователей:")
        print(f"{'ID':<6} {'Username':<20} {'Full name'}")
        print("-" * 50)
        for r in researchers:
            print(f"{r.id:<6} {r.username:<20} {r.full_name or '—'}")
        print()

        try:
            chosen_id = int(input("Введите ID исследователя: ").strip())
        except ValueError:
            print("Ошибка: введите числовой ID.")
            return

        researcher = next((r for r in researchers if r.id == chosen_id), None)
        if researcher is None:
            print(f"Ошибка: исследователь с ID {chosen_id} не найден.")
            return

        print(f"\nВыбран: [{researcher.id}] {researcher.username} ({researcher.full_name or '—'})")

        new_password = getpass.getpass("Новый пароль: ")
        if not new_password:
            print("Ошибка: пароль не может быть пустым.")
            return

        confirm = getpass.getpass("Подтвердите пароль: ")
        if new_password != confirm:
            print("Ошибка: пароли не совпадают.")
            return

        await session.execute(
            text("UPDATE users.researchers SET password_hash = :hash WHERE id = :id"),
            {"hash": hash_password(new_password), "id": chosen_id},
        )
        await session.commit()
        print(f"\nПароль успешно изменён для '{researcher.username}'.")


if __name__ == "__main__":
    asyncio.run(main())
