# utils.py — общий логгер для всех модулей
import logging
import sys

# 💡 Уровень логирования: DEBUG на dev, INFO на проде
LOG_LEVEL = logging.DEBUG

logger = logging.getLogger("gpt-support")
logger.setLevel(LOG_LEVEL)

# Вывод в консоль
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(LOG_LEVEL)

# Формат логов
formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
