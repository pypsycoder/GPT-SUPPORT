#!/usr/bin/env python
"""
Простой скрипт для проверки, были ли сохранены результаты PSQI в БД.
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, inspect, text
from app.scales.models import ScaleResult
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/hemo_db")

async def main():
    # Создаём асинхронный движок
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    # Создаём сессию
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            print("🔍 Проверяем таблицу scale_results в БД...")
            
            # Проверим, существует ли таблица
            insp = inspect(engine)
            print(f"✅ Подключение к БД: успешно\n")
            
            # Получим все записи PSQI
            stmt = select(ScaleResult).where(ScaleResult.scale_code == "PSQI").order_by(ScaleResult.measured_at.desc())
            result = await session.execute(stmt)
            psqi_records = result.scalars().all()
            
            print(f"📊 Найдено записей PSQI: {len(psqi_records)}")
            
            if psqi_records:
                print("\n📋 Последние записи PSQI:")
                for i, record in enumerate(psqi_records[:5], 1):
                    print(f"\n  Запись #{i}:")
                    print(f"    ID: {record.id}")
                    print(f"    Пользователь: {record.user_id}")
                    print(f"    Код: {record.scale_code}")
                    print(f"    Версия: {record.scale_version}")
                    print(f"    Дата: {record.measured_at}")
                    print(f"    Баллы (total_score): {record.result_json.get('total_score')}")
                    print(f"    Результат: {record.result_json.get('summary')}")
                    print(f"    Кол-во ответов: {len(record.answers_json)}")
            else:
                print("❌ Записей PSQI не найдено!")
                
            # Проверим, есть ли вообще какие-нибудь шкалы
            stmt_all = select(ScaleResult).order_by(ScaleResult.measured_at.desc())
            result_all = await session.execute(stmt_all)
            all_records = result_all.scalars().all()
            
            print(f"\n📊 Всего записей во всех шкалах: {len(all_records)}")
            
            if all_records:
                print("\n🏆 Распределение по шкалам:")
                codes = {}
                for record in all_records:
                    codes[record.scale_code] = codes.get(record.scale_code, 0) + 1
                for code, count in sorted(codes.items()):
                    print(f"  {code}: {count}")
            
            print("\n✅ Проверка завершена!\n")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
