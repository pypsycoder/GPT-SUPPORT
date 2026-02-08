#!/usr/bin/env python
"""
Reset PINs for all patients and display credentials.

Usage:
    python -m scripts.reset_all_pins

Run from the project root directory (GPT-SUPPORT/).
"""

import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db.session import async_session_factory  # noqa: E402
from app.researchers.crud import list_patients, reset_patient_pin  # noqa: E402


async def main() -> None:
    async with async_session_factory() as session:
        patients = await list_patients(session)
        
        if not patients:
            print("\nNo patients found in database.\n")
            return
        
        print(f"\n{'='*80}")
        print(f"{'RESETTING ALL PATIENT PINs AND DISPLAYING CREDENTIALS':^80}")
        print(f"{'='*80}\n")
        
        patient_creds = []
        
        for patient in patients:
            new_pin = await reset_patient_pin(session, patient)
            patient_creds.append({
                'id': patient.id,
                'name': patient.full_name,
                'number': patient.patient_number,
                'pin': new_pin,
                'token': patient.patient_token,
            })
        
        # Display table
        print(f"\n{'ID':<4} {'Name':<25} {'Number':<10} {'PIN':<6} {'Token':<35}")
        print(f"{'-'*4} {'-'*25} {'-'*10} {'-'*6} {'-'*35}")
        
        for cred in patient_creds:
            print(f"{cred['id']:<4} {cred['name']:<25} {cred['number']:<10} {cred['pin']:<6} {cred['token']:<35}")
        
        print(f"\n{'='*80}")
        print(f"\nDetailed credentials:\n")
        
        for idx, cred in enumerate(patient_creds, 1):
            print(f"Patient {idx}:")
            print(f"  ID:              {cred['id']}")
            print(f"  Name:            {cred['name']}")
            print(f"  Patient Number:  {cred['number']}")
            print(f"  PIN:             {cred['pin']} (NEW)")
            print(f"  Token:           {cred['token']}")
            print()
        
        print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
