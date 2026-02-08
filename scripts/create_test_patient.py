"""
Create a test patient (user) account.

Usage:
    python -m scripts.create_test_patient --name "Иван Иванов" --age 45 --gender "M"

Run from the project root directory (GPT-SUPPORT/).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db.session import async_session_factory  # noqa: E402
from app.researchers.crud import create_patient, list_patients  # noqa: E402


async def main(
    name: str,
    age: int | None = None,
    gender: str | None = None,
) -> None:
    """Create a test patient and display their credentials."""
    async with async_session_factory() as session:
        user, pin = await create_patient(
            session,
            full_name=name,
            age=age,
            gender=gender,
        )
        
        print("\n" + "="*60)
        print("ПАЦИЕНТ УСПЕШНО СОЗДАН")
        print("="*60)
        print(f"ID пациента:       {user.id}")
        print(f"ФИО:              {user.full_name}")
        print(f"Номер пациента:   {user.patient_number}")
        print(f"PIN-код:          {pin}")
        print(f"Токен (web):      {user.patient_token}")
        if user.age:
            print(f"Возраст:          {user.age}")
        if user.gender:
            print(f"Пол:              {user.gender}")
        print("="*60 + "\n")
        
        # Show list of all patients
        print("Все пациенты в системе:")
        print("-"*60)
        patients = await list_patients(session)
        for i, patient in enumerate(patients, 1):
            print(
                f"{i}. ID={patient.id:3d} | №={patient.patient_number:4d} | "
                f"{patient.full_name or 'Нет имени'}"
            )
        print("-"*60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Создать тестового пациента")
    parser.add_argument(
        "--name",
        required=True,
        help="ФИО пациента (обязательно)",
    )
    parser.add_argument(
        "--age",
        type=int,
        default=None,
        help="Возраст (необязательно)",
    )
    parser.add_argument(
        "--gender",
        choices=["M", "F"],
        default=None,
        help="Пол: M (мужской) или F (женский) (необязательно)",
    )

    args = parser.parse_args()
    asyncio.run(main(args.name, args.age, args.gender))
