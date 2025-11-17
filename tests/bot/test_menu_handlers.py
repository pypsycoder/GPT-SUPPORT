import pytest
from types import SimpleNamespace

pytestmark = pytest.mark.asyncio


class DummyMessage:
    def __init__(self, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=203627906, full_name="Test User")
        self._answers = []

    async def answer(self, text, reply_markup=None):
        self._answers.append(text)

    @property
    def last_answer(self):
        return self._answers[-1] if self._answers else None


async def call(handler, text):
    msg = DummyMessage(text=text)
    await handler(msg)
    return msg


def import_menu():
    from app.bots.tg_bot.routers.menu import (
        cmd_menu,
        open_scales,
        open_profile,
        open_learning,
        open_diary,
        open_help,
        diary_add_pulse,
    )

    return (
        cmd_menu,
        open_scales,
        open_profile,
        open_learning,
        open_diary,
        open_help,
        diary_add_pulse,
    )


async def _assert_contains(msg, needle):
    assert msg.last_answer and needle in msg.last_answer


async def test_cmd_menu():
    cmd_menu, *_ = import_menu()
    msg = await call(cmd_menu, "/menu_reply")
    await _assert_contains(msg, "Главное меню:")


async def test_open_sections():
    _, open_scales, open_profile, open_learning, open_diary, open_help, _ = import_menu()
    msg = await call(open_scales, "🧪 Шкалы")
    await _assert_contains(msg, "Шкалы")
    msg = await call(open_profile, "👤 Профиль")
    await _assert_contains(msg, "Профиль")
    msg = await call(open_learning, "📚 Обучение")
    await _assert_contains(msg, "Обучение")
    msg = await call(open_diary, "📒 Дневник")
    await _assert_contains(msg, "Дневник")
    msg = await call(open_help, "❓ Помощь")
    await _assert_contains(msg, "Помощь")


async def test_diary_add_pulse():
    from app.bots.tg_bot.routers.menu import diary_add_pulse

    msg = await call(diary_add_pulse, "➕ Ввести пульс")
    await _assert_contains(msg, "Введите пульс")
