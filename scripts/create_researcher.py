"""
Create a researcher account.

Usage:
    python -m scripts.create_researcher --username admin --password secret --name "Иванов И.И."

Run from the project root directory (GPT-SUPPORT/).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db.session import async_session_factory  # noqa: E402
from app.researchers.crud import create_researcher, get_researcher_by_username  # noqa: E402


async def main(username: str, password: str, full_name: str | None) -> None:
    async with async_session_factory() as session:
        existing = await get_researcher_by_username(session, username)
        if existing:
            print(f"Исследователь '{username}' уже существует (id={existing.id})")
            return

        researcher = await create_researcher(
            session,
            username=username,
            password=password,
            full_name=full_name,
        )
        print(f"Исследователь создан: id={researcher.id}, username={researcher.username}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Создать аккаунт исследователя")
    parser.add_argument("--username", required=True, help="Логин")
    parser.add_argument("--password", required=True, help="Пароль")
    parser.add_argument("--name", default=None, help="ФИО (необязательно)")

    args = parser.parse_args()
    asyncio.run(main(args.username, args.password, args.name))
