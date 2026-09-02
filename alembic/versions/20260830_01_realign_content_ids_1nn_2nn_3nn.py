"""Realign education & practices identifiers to the 1NN/2NN/3NN scheme

Revision ID: 20260830_01
Revises: 20260829_01
Create Date: 2026-08-30

Контент в content/ переведён на трёхзначную схему идентификаторов
(1NN — психология, 2NN — гемодиализ, 3NN — сквозной блок; первая цифра = блок).
БД отставала. Ревизия приводит идентификаторы в БД к той же схеме, НЕ трогая
содержимое уроков/тестов/практик и НЕ теряя пользовательских данных.

Что меняется
------------
* education.lessons              — code + order_index (17 строк)
* education.lesson_tests         — code (17 строк)
* practices.practices            — id (p01_* → pNNN) + module_id ('01' → '101'), 12 строк
* practices.practice_completions — practice_id (ссылочное поле идёт за practices.id), 9 строк

Что НЕ трогаем
--------------
* education.lesson_progress.lesson_id и education.lesson_test_results.test_id
  ссылаются на суррогатные integer-PK (lessons.id / lesson_tests.id), которые
  не меняются, — эти таблицы с пользовательскими данными едут следом автоматически.
* Тексты карточек, вопросов, инструкций практик — задача только про идентификаторы.

Ключи сопоставления
-------------------
Строки ищутся по СТАРОМУ значению естественного ключа, а не по суррогатному id
(он свой в каждой среде): уроки/тесты — по старому уникальному `code`, практики —
по старому строковому PK `id`. Если строки нет (среда уже на новой схеме или урок
не импортирован) — UPDATE затронет 0 строк, это безопасно.

FK practices.practice_completions.practice_id
--------------------------------------------
fk_pc_practice_id объявлен ON UPDATE NO ACTION, поэтому UPDATE practices.id нарушил
бы его немедленно. Путь: снять FK → обновить practices.id и practice_completions.
practice_id → пересоздать FK с тем же ON DELETE CASCADE. Всё внутри одной транзакции
ревизии; семантика FK сохраняется (без перехода на ON UPDATE CASCADE, который пережил
бы миграцию). Полностью реверсивно.

Карты старых↔новых значений зашиты константами здесь, а не читаются из content/ —
downgrade не должен зависеть от изменяемых файлов.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_01"
down_revision: Union[str, Sequence[str], None] = "20260829_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (old_code, old_order_index, new_code, new_order_index)
LESSONS: list[tuple[str, int, str, int]] = [
    # 1NN — психология: order 1..9 → 101..109
    ("01_stress", 1, "101_stress", 101),
    ("02_emocii", 2, "102_emocii", 102),
    ("03_trevoga", 3, "103_trevoga", 103),
    ("04_son", 4, "104_son", 104),
    ("05_koping-strategii", 5, "105_koping-strategii", 105),
    ("06_motivaciya", 6, "106_motivaciya", 106),
    ("07_kognitivnye-sposobnosti", 7, "107_kognitivnye-sposobnosti", 107),
    ("08_emocionalnoe-vygoranie", 8, "108_emocionalnoe-vygoranie", 108),
    ("09_adaptaciya-k-hronicheskoy-bolezni", 9, "109_adaptaciya-k-hronicheskoy-bolezni", 109),
    # 2NN — гемодиализ: order 1..8 → 202..209 (201 «Что такое гемодиализ» — черновик, в БД нет)
    ("01_pitanie-i-dieta", 1, "202_pitanie-i-dieta", 202),
    ("02_zhidkost-i-vodnyy-balans", 2, "203_zhidkost-i-vodnyy-balans", 203),
    ("03_preparaty", 3, "204_preparaty", 204),
    ("04_fizicheskaya-aktivnost", 4, "205_fizicheskaya-aktivnost", 205),
    ("05_sosudistyy-dostup-fistula", 5, "206_sosudistyy-dostup-fistula", 206),
    ("06_simptomy-i-oslozhneniya", 6, "207_simptomy-i-oslozhneniya", 207),
    ("07_laboratornye-pokazateli", 7, "208_laboratornye-pokazateli", 208),
    ("08_zhizn-s-dializom", 8, "209_zhizn-s-dializom", 209),
]

# (old_code, new_code)
LESSON_TESTS: list[tuple[str, str]] = [
    ("01_stress-test", "101_stress-test"),
    ("02_emocii-test", "102_emocii-test"),
    ("03_trevoga-test", "103_trevoga-test"),
    ("04_son-test", "104_son-test"),
    ("05_koping-test", "105_koping-test"),
    ("06_motivaciya-test", "106_motivaciya-test"),
    ("07_kognitivnye-test", "107_kognitivnye-test"),
    ("08_vygoranie-test", "108_vygoranie-test"),
    ("09_adaptaciya-test", "109_adaptaciya-test"),
    ("11_pitanie-test", "202_pitanie-test"),
    ("12_zhidkost-test", "203_zhidkost-test"),
    ("13_preparaty-test", "204_preparaty-test"),
    ("14_aktivnost-test", "205_aktivnost-test"),
    ("15_fistula-test", "206_fistula-test"),
    ("16_simptomy-test", "207_simptomy-test"),
    ("17_laboratoriya-test", "208_laboratoriya-test"),
    ("18_zhizn-s-dializom-test", "209_zhizn-s-dializom-test"),
]

# (old_id, old_module_id, new_id, new_module_id) — сопоставление по title/module (PRACTICE_ID_MAP.json)
PRACTICES: list[tuple[str, str, str, str]] = [
    ("p01_breathing_478", "01", "p101", "101"),  # 4-7-8: дыхание для разгрузки
    ("p02_body_54321", "02", "p102", "102"),     # Заземление 5-4-3-2-1
    ("p03_breathing", "03", "p103", "103"),      # Квадратное дыхание
    ("p04_body", "04", "p104", "104"),           # Расслабление тела перед сном
    ("p05_behavioral", "05", "p105", "105"),     # Три варианта
    ("p06_behavioral", "06", "p106", "106"),     # Две минуты — и достаточно
    ("p07_behavioral", "07", "p107", "107"),     # Три дела на завтра
    ("p08_breathing", "08", "p108", "108"),      # Физиологический вздох
    ("p09_body", "09", "p109", "109"),           # Три вещи которые тело сделало сегодня
    ("p10_body", "10", "p110", "102"),           # Сжать и отпустить      (эмоции: злость)
    ("p11_cognitive", "11", "p111", "102"),      # Скажи себе как другу   (эмоции: грусть)
    ("p12_body", "12", "p112", "102"),           # Холодный якорь         (эмоции: страх)
]

_PC_FK = "fk_pc_practice_id"


def _apply_lessons(conn, *, forward: bool) -> None:
    for old_code, old_oi, new_code, new_oi in LESSONS:
        key, code, oi = (
            (old_code, new_code, new_oi) if forward else (new_code, old_code, old_oi)
        )
        conn.execute(
            sa.text(
                "UPDATE education.lessons SET code = :code, order_index = :oi "
                "WHERE code = :key"
            ),
            {"code": code, "oi": oi, "key": key},
        )


def _apply_tests(conn, *, forward: bool) -> None:
    for old_code, new_code in LESSON_TESTS:
        key, code = (old_code, new_code) if forward else (new_code, old_code)
        conn.execute(
            sa.text("UPDATE education.lesson_tests SET code = :code WHERE code = :key"),
            {"code": code, "key": key},
        )


def _apply_practices(conn, *, forward: bool) -> None:
    op.drop_constraint(_PC_FK, "practice_completions", schema="practices", type_="foreignkey")
    for old_id, old_mod, new_id, new_mod in PRACTICES:
        src, dst, mod = (
            (old_id, new_id, new_mod) if forward else (new_id, old_id, old_mod)
        )
        conn.execute(
            sa.text(
                "UPDATE practices.practices SET id = :dst, module_id = :mod WHERE id = :src"
            ),
            {"dst": dst, "mod": mod, "src": src},
        )
        conn.execute(
            sa.text(
                "UPDATE practices.practice_completions SET practice_id = :dst "
                "WHERE practice_id = :src"
            ),
            {"dst": dst, "src": src},
        )
    op.create_foreign_key(
        _PC_FK,
        "practice_completions",
        "practices",
        ["practice_id"],
        ["id"],
        source_schema="practices",
        referent_schema="practices",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    conn = op.get_bind()
    _apply_lessons(conn, forward=True)
    _apply_tests(conn, forward=True)
    _apply_practices(conn, forward=True)


def downgrade() -> None:
    conn = op.get_bind()
    _apply_practices(conn, forward=False)
    _apply_tests(conn, forward=False)
    _apply_lessons(conn, forward=False)
