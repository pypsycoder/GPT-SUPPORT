# app/users/utils.py
# Вспомогательные функции для работы с пользователями.

import secrets


# generate_patient_token
def generate_patient_token() -> str:
    """
    Генерирует безопасный URL-friendly токен для пациента.

    Используем secrets.token_urlsafe, чтобы получить криптографически
    стойкую случайную строку, затем обрезаем до разумной длины.
    """
    raw_token = secrets.token_urlsafe(32)  # длина ~43 символа
    # Обрезаем до 32 символов, чтобы токен был компактнее в URL.
    return raw_token[:32]
