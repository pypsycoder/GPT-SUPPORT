"""
Быстрый тест парсера import_md_v2.
Запуск: python test_parser.py
Зависимости: только stdlib, SQLAlchemy не нужна.
"""

import json
import sys
from pathlib import Path

# Добавляем путь если запускаем отдельно
sys.path.insert(0, str(Path(__file__).parent))

from education_parser import parse_lesson_markdown, validate_lesson_md

# =========================
#  ТЕСТОВЫЙ MD
# =========================

TEST_MD = """
# 😴 Усталость после диализа

## [recognition] После диализа хочется чтобы все отстали

Вы возвращаетесь домой и хочется просто лечь.
Это не плохой характер. Это тело говорит вам кое-что важное.

## [mechanism] Почему это происходит

Во время диализа организм работает как двигатель на максимальных оборотах.
Неудивительно, что после нужно время остыть.

## [empowerment] Вы уже знаете свой ритм

Скорее всего, вы уже нашли способ восстанавливаться.
Поспать, поесть что-то лёгкое, побыть в тишине.
Это не лень — это именно то, что нужно телу.

## [deepdive] Питание в этот момент

После диализа организму нужно лёгкое и питательное.
Тяжёлая еда создаёт дополнительную нагрузку.

## [deepdive] Как объяснить близким

Близким бывает трудно понять, почему вы «просто лежите».
Простая фраза помогает: «Мне нужен час — потом я с вами».

## [actions] Попробуйте одно из этого

> Дайте себе 20 минут лёжа — без телефона и дел
> Скажите близким заранее: «Мне нужен час»
> Держите дома что-то лёгкое специально для этого момента
> Заведите короткий ритуал — тело привыкает к сигналам

## [anchor] Что отслеживать в приложении

Замечайте, как меняется усталость со временем.
В разделе «Активность» можно фиксировать самочувствие после каждого сеанса.
"""

# =========================
#  ТЕСТЫ
# =========================

def test_card_count():
    cards = parse_lesson_markdown(TEST_MD)
    assert len(cards) == 7, f"Ожидали 7 карточек, получили {len(cards)}"
    print(f"✅ Количество карточек: {len(cards)}")

def test_card_types():
    cards = parse_lesson_markdown(TEST_MD)
    expected_types = [
        "recognition",
        "mechanism",
        "empowerment",
        "deepdive",
        "deepdive",
        "actions",
        "anchor",
    ]
    actual_types = [c.card_type for c in cards]
    assert actual_types == expected_types, \
        f"Типы не совпадают:\nОжидали: {expected_types}\nПолучили: {actual_types}"
    print(f"✅ Типы карточек: {actual_types}")

def test_actions_parsed():
    cards = parse_lesson_markdown(TEST_MD)
    actions_card = next(c for c in cards if c.card_type == "actions")

    assert actions_card.actions_json is not None, "actions_json не заполнен"
    items = json.loads(actions_card.actions_json)
    assert len(items) == 4, f"Ожидали 4 варианта, получили {len(items)}"
    assert items[0] == "Дайте себе 20 минут лёжа — без телефона и дел"
    print(f"✅ Actions JSON: {items}")

def test_actions_content_md():
    """content_md у actions-карточки не должен содержать строки >"""
    cards = parse_lesson_markdown(TEST_MD)
    actions_card = next(c for c in cards if c.card_type == "actions")
    assert ">" not in actions_card.content_md, \
        "content_md содержит строки > — парсер не вычистил"
    print(f"✅ content_md actions-карточки чист: '{actions_card.content_md}'")

def test_titles():
    cards = parse_lesson_markdown(TEST_MD)
    assert cards[0].title == "После диализа хочется чтобы все отстали"
    assert cards[5].title == "Попробуйте одно из этого"
    print(f"✅ Заголовки карточек корректны")

def test_no_type_fallback():
    """Карточка без [type] получает card_type='text'"""
    md = """
## Просто заголовок без типа

Текст карточки.
"""
    cards = parse_lesson_markdown(md)
    assert cards[0].card_type == "text"
    assert cards[0].title == "Просто заголовок без типа"
    print(f"✅ Fallback на 'text' работает")

def test_unknown_type_fallback():
    """Неизвестный тип не ломает парсер"""
    md = """
## [unknowntype] Заголовок

Текст.
"""
    cards = parse_lesson_markdown(md)
    assert cards[0].card_type == "text"
    print(f"✅ Неизвестный тип → fallback на 'text'")

# =========================
#  ЗАПУСК
# =========================

if __name__ == "__main__":
    tests = [
        test_card_count,
        test_card_types,
        test_actions_parsed,
        test_actions_content_md,
        test_titles,
        test_no_type_fallback,
        test_unknown_type_fallback,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {test.__name__} упал с ошибкой: {e}")
            failed += 1

    print(f"\n{'='*40}")
    if failed == 0:
        print(f"✅ Все тесты прошли ({len(tests)}/{len(tests)})")
    else:
        print(f"❌ Провалилось: {failed}/{len(tests)}")
        sys.exit(1)
