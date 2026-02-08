#!/usr/bin/env python
"""
Create a test patient/user with PIN-based authentication.

Usage:
    python -m scripts.create_test_user --name "Иван Иванов" --age 45 --gender "M"

Run from the project root directory (GPT-SUPPORT/).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db.session import async_session_factory  # noqa: E402
from app.researchers.crud import create_patient  # noqa: E402


async def main(full_name: str, age: int | None, gender: str | None) -> None:
    async with async_session_factory() as session:
        user, pin = await create_patient(
            session,
            full_name=full_name,
            age=age,
            gender=gender,
        )
        print(f"\n{'='*60}")
        print(f"Patient created successfully!")
        print(f"{'='*60}")
        print(f"Patient ID:       {user.id}")
        print(f"Full Name:        {user.full_name}")
        print(f"Patient Number:   {user.patient_number}")
        print(f"PIN:              {pin}")
        print(f"Patient Token:    {user.patient_token}")
        print(f"Age:              {user.age}")
        print(f"Gender:           {user.gender}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a test patient account")
    parser.add_argument("--name", required=True, help="Full name of patient")
    parser.add_argument("--age", type=int, default=None, help="Age (optional)")
    parser.add_argument("--gender", default=None, help="Gender (optional)")

    args = parser.parse_args()
    asyncio.run(main(args.name, args.age, args.gender))
