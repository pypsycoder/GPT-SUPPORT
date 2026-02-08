#!/usr/bin/env python
"""
Display test credentials for quick reference.

This script shows the current test accounts and their login credentials.

Usage:
    python -m scripts.show_credentials

Run from the project root directory (GPT-SUPPORT/).
"""

import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db.session import async_session_factory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.users.models import User  # noqa: E402
from app.researchers.models import Researcher  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        # Get all researchers
        researchers = await session.execute(select(Researcher).order_by(Researcher.id))
        researchers = researchers.scalars().all()
        
        # Get all patients
        patients = await session.execute(select(User).order_by(User.id))
        patients = patients.scalars().all()
        
        print("\n" + "="*80)
        print("TEST CREDENTIALS FOR GPT-SUPPORT".center(80))
        print("="*80 + "\n")
        
        if researchers:
            print("RESEARCHERS:")
            print("-" * 80)
            for r in researchers:
                print(f"  Username:    {r.username}")
                print(f"  Full Name:   {r.full_name or '(not set)'}")
                print(f"  ID:          {r.id}")
                print()
        
        if patients:
            print("PATIENTS:")
            print("-" * 80)
            for p in patients:
                print(f"  ID:             {p.id}")
                print(f"  Name:           {p.full_name or '(not set)'}")
                print(f"  Patient Number: {p.patient_number}")
                print(f"  Age:            {p.age or '(not set)'}")
                print(f"  Gender:         {p.gender or '(not set)'}")
                print(f"  Token:          {p.patient_token}")
                print(f"  Locked:         {'Yes' if p.is_locked else 'No'}")
                print()
        
        if not researchers and not patients:
            print("No test accounts found. Run the creation scripts first:")
            print("  python -m scripts.create_researcher --username testadmin --password admin123")
            print("  python -m scripts.create_test_user --name 'Test Patient' --age 45 --gender M")
        
        print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
