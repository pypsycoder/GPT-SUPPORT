import pytest
from types import SimpleNamespace

pytestmark = pytest.mark.asyncio


class DummyMessage:
    def __init__(self, text=""):
        self.text = text
        self.from_user = SimpleNamespace(id=203627906, full_name="Test User")
        self._answers = []
        self._edited = []

    async def answer(self, text, reply_markup=None):
        self._answers.append(text)

    async def edit_text(self, text, reply_markup=None):
        self._edited.append(text)

    @property
    def last_answer(self):
        return self._answers[-1] if self._answers else None

    @property
    def last_edited(self):
        return self._edited[-1] if self._edited else None


class DummyCallback:
    def __init__(self, data):
        self.data = data
        self.message = DummyMessage()

    async def answer(self):
        pass


def import_menu():
    from app.bot.routers.menu_inline import cmd_menu, open_scales, nav_home
    return cmd_menu, open_scales, nav_home


async def test_cmd_menu():
    cmd_menu, *_ = import_menu()
    msg = DummyMessage("/menu")
    await cmd_menu(msg)
    assert "Главное меню:" in msg.last_answer


async def test_open_scales_edits_message():
    _, open_scales, nav_home = import_menu()
    cb = DummyCallback("menu:scales")
    await open_scales(cb)
    assert "Шкалы" in cb.message.last_edited
    # проверим возврат домой
    cb_home = DummyCallback("nav:home")
    await nav_home(cb_home)
    assert "Главное меню:" in cb_home.message.last_edited
