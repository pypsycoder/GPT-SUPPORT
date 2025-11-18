from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.users.crud import get_user_by_telegram_id, save_user
from app.vitals import crud, service
from bots.shared.utils import logger
from core.db.session import async_session_factory

router = Router()


async def _get_or_create_user(session, message: Message):
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        user = await save_user(session, telegram_id, full_name)
        await session.commit()
    return user


@router.message(Command("bp"))
async def handle_bp(message: Message):
    if not message.text:
        return
    async with async_session_factory() as session:
        user = await _get_or_create_user(session, message)
        systolic, diastolic = service.VitalsService.parse_bp_text(message.text.replace("/bp", ""))
        payload = service.VitalsService.prepare_bp_data(
            user_id=user.id,
            systolic=systolic,
            diastolic=diastolic,
            measured_at=datetime.now(timezone.utc),
        )
        await crud.bp_crud.create(session, payload)
        await session.commit()
    logger.info("[vitals][bp] measurement saved")
    await message.answer("Давление сохранено ✅")


@router.message(Command("pulse"))
async def handle_pulse(message: Message):
    if not message.text:
        return
    async with async_session_factory() as session:
        user = await _get_or_create_user(session, message)
        bpm = service.VitalsService.parse_int(message.text.replace("/pulse", ""))
        payload = service.VitalsService.prepare_pulse_data(
            user_id=user.id,
            bpm=bpm,
            measured_at=datetime.now(timezone.utc),
        )
        await crud.pulse_crud.create(session, payload)
        await session.commit()
    logger.info("[vitals][pulse] measurement saved")
    await message.answer("Пульс сохранён ✅")


@router.message(Command("weight"))
async def handle_weight(message: Message):
    if not message.text:
        return
    async with async_session_factory() as session:
        user = await _get_or_create_user(session, message)
        weight = service.VitalsService.parse_float(message.text.replace("/weight", ""))
        payload = service.VitalsService.prepare_weight_data(
            user_id=user.id,
            weight=weight,
            measured_at=datetime.now(timezone.utc),
        )
        await crud.weight_crud.create(session, payload)
        await session.commit()
    logger.info("[vitals][weight] measurement saved")
    await message.answer("Вес сохранён ✅")


@router.message(Command("temperature"))
async def handle_temperature(message: Message):
    if not message.text:
        return
    async with async_session_factory() as session:
        user = await _get_or_create_user(session, message)
        temperature = service.VitalsService.parse_float(message.text.replace("/temperature", ""))
        payload = service.VitalsService.prepare_temperature_data(
            user_id=user.id,
            temperature=temperature,
            measured_at=datetime.now(timezone.utc),
        )
        await crud.temperature_crud.create(session, payload)
        await session.commit()
    logger.info("[vitals][temperature] measurement saved")
    await message.answer("Температура сохранена ✅")
