# ============================================
# Medications seed: справочник препаратов
# ============================================

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.medications.models import MedicationReference

MEDICATION_SEED_DATA = [
    {"name_ru": "Севеламер", "name_trade": "Ренагель, Селамерекс, Севеламера карбонат", "category": "phosphate_binder", "typical_doses": ["800 мг", "400 мг"], "food_relation_hint": "with", "search_keywords": "sevelamer ренагель фосфат", "sort_order": 10},
    {"name_ru": "Кальция ацетат", "name_trade": "Нефрос, Фосренол", "category": "phosphate_binder", "typical_doses": ["667 мг", "950 мг"], "food_relation_hint": "with", "sort_order": 11},
    {"name_ru": "Кальция карбонат", "name_trade": None, "category": "phosphate_binder", "typical_doses": ["500 мг", "1000 мг"], "food_relation_hint": "with", "sort_order": 12},
    {"name_ru": "Лантана карбонат", "name_trade": "Фосренол", "category": "phosphate_binder", "typical_doses": ["500 мг", "750 мг", "1000 мг"], "food_relation_hint": "with", "sort_order": 13},
    {"name_ru": "Амлодипин", "name_trade": "Норваск, Амловас, Тенокс", "category": "antihypertensive", "typical_doses": ["5 мг", "10 мг"], "food_relation_hint": "none", "sort_order": 20},
    {"name_ru": "Лизиноприл", "name_trade": "Диротон, Лизинотон", "category": "antihypertensive", "typical_doses": ["5 мг", "10 мг", "20 мг"], "food_relation_hint": "none", "sort_order": 21},
    {"name_ru": "Лозартан", "name_trade": "Козаар, Лозап, Лориста", "category": "antihypertensive", "typical_doses": ["50 мг", "100 мг"], "food_relation_hint": "none", "sort_order": 22},
    {"name_ru": "Бисопролол", "name_trade": "Конкор, Бипрол, Коронал", "category": "antihypertensive", "typical_doses": ["2.5 мг", "5 мг", "10 мг"], "food_relation_hint": "none", "sort_order": 23},
    {"name_ru": "Метопролол", "name_trade": "Эгилок, Беталок", "category": "antihypertensive", "typical_doses": ["25 мг", "50 мг", "100 мг"], "food_relation_hint": "none", "sort_order": 24},
    {"name_ru": "Карведилол", "name_trade": "Дилатренд, Кориол", "category": "antihypertensive", "typical_doses": ["6.25 мг", "12.5 мг", "25 мг"], "food_relation_hint": "with", "sort_order": 25},
    {"name_ru": "Нифедипин", "name_trade": "Коринфар, Кордафлекс", "category": "antihypertensive", "typical_doses": ["10 мг", "20 мг", "30 мг"], "food_relation_hint": "none", "sort_order": 26},
    {"name_ru": "Доксазозин", "name_trade": "Кардура, Артезин", "category": "antihypertensive", "typical_doses": ["1 мг", "2 мг", "4 мг"], "food_relation_hint": "none", "sort_order": 27},
    {"name_ru": "Моксонидин", "name_trade": "Физиотенз, Моксарел", "category": "antihypertensive", "typical_doses": ["0.2 мг", "0.4 мг"], "food_relation_hint": "none", "sort_order": 28},
    {"name_ru": "Эпоэтин альфа", "name_trade": "Эпрекс, Эральфон", "category": "esa", "typical_doses": ["2000 МЕ", "4000 МЕ", "10000 МЕ"], "food_relation_hint": "none", "sort_order": 30},
    {"name_ru": "Эпоэтин бета", "name_trade": "Рекормон", "category": "esa", "typical_doses": ["2000 МЕ", "4000 МЕ", "10000 МЕ"], "food_relation_hint": "none", "sort_order": 31},
    {"name_ru": "Дарбэпоэтин альфа", "name_trade": "Аранесп", "category": "esa", "typical_doses": ["20 мкг", "40 мкг", "60 мкг"], "food_relation_hint": "none", "sort_order": 32},
    {"name_ru": "Метокси-ПЭГ эпоэтин бета", "name_trade": "Мирцера", "category": "esa", "typical_doses": ["50 мкг", "100 мкг", "150 мкг"], "food_relation_hint": "none", "sort_order": 33},
    {"name_ru": "Железа сахарат", "name_trade": "Венофер", "category": "iron", "typical_doses": ["100 мг", "200 мг"], "food_relation_hint": "none", "sort_order": 40},
    {"name_ru": "Железа карбоксимальтозат", "name_trade": "Феринжект", "category": "iron", "typical_doses": ["500 мг", "1000 мг"], "food_relation_hint": "none", "sort_order": 41},
    {"name_ru": "Железа сульфат", "name_trade": "Сорбифер, Тардиферон", "category": "iron", "typical_doses": ["100 мг", "320 мг"], "food_relation_hint": "before", "sort_order": 42},
    {"name_ru": "Кальцитриол", "name_trade": "Рокальтрол, Остеотриол", "category": "vitamin_d", "typical_doses": ["0.25 мкг", "0.5 мкг"], "food_relation_hint": "none", "sort_order": 50},
    {"name_ru": "Альфакальцидол", "name_trade": "Альфа Д3-Тева, Оксидевит", "category": "vitamin_d", "typical_doses": ["0.25 мкг", "0.5 мкг", "1 мкг"], "food_relation_hint": "none", "sort_order": 51},
    {"name_ru": "Парикальцитол", "name_trade": "Земплар", "category": "vitamin_d", "typical_doses": ["1 мкг", "2 мкг", "4 мкг"], "food_relation_hint": "none", "sort_order": 52},
    {"name_ru": "Колекальциферол", "name_trade": "Аквадетрим, Вигантол", "category": "vitamin_d", "typical_doses": ["500 МЕ", "1000 МЕ", "2000 МЕ"], "food_relation_hint": "with", "sort_order": 53},
    {"name_ru": "Цинакальцет", "name_trade": "Мимпара, Сенсипар", "category": "calcimimetic", "typical_doses": ["30 мг", "60 мг", "90 мг"], "food_relation_hint": "with", "sort_order": 60},
    {"name_ru": "Этелкальцетид", "name_trade": "Парсабив", "category": "calcimimetic", "typical_doses": ["2.5 мг", "5 мг", "10 мг"], "food_relation_hint": "none", "sort_order": 61},
    {"name_ru": "Фуросемид", "name_trade": "Лазикс", "category": "diuretic", "typical_doses": ["40 мг", "80 мг", "120 мг"], "food_relation_hint": "before", "sort_order": 70},
    {"name_ru": "Торасемид", "name_trade": "Диувер, Тригрим", "category": "diuretic", "typical_doses": ["5 мг", "10 мг", "20 мг"], "food_relation_hint": "none", "sort_order": 71},
    {"name_ru": "Патиромер", "name_trade": "Велтасса", "category": "potassium_binder", "typical_doses": ["8.4 г", "16.8 г", "25.2 г"], "food_relation_hint": "with", "sort_order": 80},
    {"name_ru": "Натрия циркония циклосиликат", "name_trade": "Локелма", "category": "potassium_binder", "typical_doses": ["5 г", "10 г"], "food_relation_hint": "none", "sort_order": 81},
    {"name_ru": "Полистиролсульфонат натрия", "name_trade": "Кайексалат", "category": "potassium_binder", "typical_doses": ["15 г", "30 г"], "food_relation_hint": "none", "sort_order": 82},
    {"name_ru": "Варфарин", "name_trade": "Варфарекс", "category": "anticoagulant", "typical_doses": ["2.5 мг", "5 мг"], "food_relation_hint": "none", "sort_order": 90},
    {"name_ru": "Ривароксабан", "name_trade": "Ксарелто", "category": "anticoagulant", "typical_doses": ["10 мг", "15 мг", "20 мг"], "food_relation_hint": "with", "sort_order": 91},
    {"name_ru": "Апиксабан", "name_trade": "Эликвис", "category": "anticoagulant", "typical_doses": ["2.5 мг", "5 мг"], "food_relation_hint": "none", "sort_order": 92},
    {"name_ru": "Омепразол", "name_trade": "Омез, Лосек", "category": "other", "typical_doses": ["20 мг", "40 мг"], "food_relation_hint": "before", "sort_order": 100},
    {"name_ru": "Пантопразол", "name_trade": "Нольпаза, Контролок", "category": "other", "typical_doses": ["20 мг", "40 мг"], "food_relation_hint": "before", "sort_order": 101},
    {"name_ru": "Аторвастатин", "name_trade": "Липримар, Аторис", "category": "other", "typical_doses": ["10 мг", "20 мг", "40 мг"], "food_relation_hint": "none", "sort_order": 102},
    {"name_ru": "Розувастатин", "name_trade": "Крестор, Розукард", "category": "other", "typical_doses": ["5 мг", "10 мг", "20 мг"], "food_relation_hint": "none", "sort_order": 103},
    {"name_ru": "Ацетилсалициловая кислота", "name_trade": "Аспирин, Тромбо АСС, КардиАСК", "category": "other", "typical_doses": ["75 мг", "100 мг", "150 мг"], "food_relation_hint": "after", "sort_order": 104},
    {"name_ru": "Клопидогрел", "name_trade": "Плавикс, Зилт", "category": "other", "typical_doses": ["75 мг"], "food_relation_hint": "none", "sort_order": 105},
    {"name_ru": "Аллопуринол", "name_trade": None, "category": "other", "typical_doses": ["100 мг", "300 мг"], "food_relation_hint": "after", "sort_order": 106},
    {"name_ru": "Фолиевая кислота", "name_trade": None, "category": "other", "typical_doses": ["1 мг", "5 мг"], "food_relation_hint": "none", "sort_order": 107},
    {"name_ru": "Витамин B12 (цианокобаламин)", "name_trade": None, "category": "other", "typical_doses": ["500 мкг", "1000 мкг"], "food_relation_hint": "none", "sort_order": 108},
]


async def seed_medication_references(session: AsyncSession) -> int:
    """
    Заполнить справочник препаратов, если он пуст.
    Идемпотентно: не дублирует по name_ru.
    Возвращает количество добавленных записей.
    """
    result = await session.execute(select(MedicationReference).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0
    added = 0
    for row in MEDICATION_SEED_DATA:
        ref = MedicationReference(
            name_ru=row["name_ru"],
            name_trade=row.get("name_trade"),
            category=row["category"],
            typical_doses=row.get("typical_doses") or [],
            food_relation_hint=row.get("food_relation_hint"),
            search_keywords=row.get("search_keywords"),
            sort_order=row.get("sort_order", 100),
        )
        session.add(ref)
        added += 1
    return added
