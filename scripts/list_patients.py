#!/usr/bin/env python
"""
List all patients with their credentials.

Usage:
    python -m scripts.list_patients

Run from the project root directory (GPT-SUPPORT/).
"""

import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db.session import async_session_factory  # noqa: E402
from app.researchers.crud import list_patients  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        patients = await list_patients(session)
        
        if not patients:
            print("\nNo patients found in database.\n")
            return
        
        print(f"\n{'='*80}")
        print(f"{'PATIENTS LIST':^80}")
        print(f"{'='*80}\n")
        
        for idx, patient in enumerate(patients, 1):
            print(f"Patient #{idx}:")
            print(f"  ID:              {patient.id}")
            print(f"  Full Name:       {patient.full_name}")
            print(f"  Patient Number:  {patient.patient_number}")
            print(f"  PIN Hash:        {patient.pin_hash[:16]}..." if patient.pin_hash else "  PIN Hash:        (not set)")
            print(f"  Patient Token:   {patient.patient_token}")
            print(f"  Age:             {patient.age}")
            print(f"  Gender:          {patient.gender}")
            print(f"  Locked:          {patient.is_locked}")
            print()
        
        print(f"{'='*80}")
        print(f"Total patients: {len(patients)}")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
