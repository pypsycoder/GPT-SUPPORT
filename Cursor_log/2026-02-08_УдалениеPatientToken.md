**Задача:** Убрать patient_token из системы полностью

**Дата:** 2026-02-08

**Действия:**
- Education: в моделях LessonProgress и LessonTestResult поле patient_token заменено на user_id (FK на users.users.id). Роутер и profile service переведены на user.id.
- User: из модели удалено поле patient_token. Auth /patient/me больше не возвращает patient_token. Удалены генерация и подстановка токена в dependencies.
- Users API: удалён эндпоинт GET /patients/by-token/{patient_token}. CRUD: удалены get_user_by_patient_token и передача patient_token при создании пользователя.
- Researchers: при создании пациента больше не задаётся patient_token.
- Profile: из схемы и сервиса убрано поле patient_token; блок «Токен доступа» удалён с фронта профиля.
- Vitals: добавлены сессионные эндпоинты GET/POST /vitals/bp/me, /pulse/me, /weight/me, POST/GET /vitals/water/me, GET /vitals/water/daily-total/me (схемы *CreateMe без user_id). Все by-token эндпоинты удалены.
- Frontend: убраны getPatientToken, отображение и копирование токена. Виталы и главная используют только /me с credentials: 'include'. Обучение, шкалы, профиль — только сессия.
- Legacy маршруты /p/{token}/... оставлены (отдают те же HTML; вход по PIN).
- Миграция a1b2c3d4e5f6: в education добавлен user_id, данные перенесены с patient_token, колонки patient_token удалены; из users удалён patient_token.
- Скрипты и тест: убраны вывод и использование patient_token.

**Файлы:** app/education/models.py, router.py; app/users/models.py, crud.py, api.py, schemas.py, utils.py; app/auth/dependencies.py, router.py; app/profile/service.py, schemas.py; app/vitals/router.py, schemas.py; app/researchers/crud.py, schemas.py; frontend (vitals, home, auth, profile, education*, hads, tobol, kop25a, psqi); alembic/versions/a1b2c3d4e5f6_remove_patient_token.py; scripts/*; tests/test_scales_tobol.py.

**Результат:** Идентификация пациента только по сессии (номер + PIN). Токен в URL и в запросах не используется.

**Проблемы:** После применения миграции старые ссылки /p/{token}/... по-прежнему открывают страницы, но для доступа к данным нужен вход по номеру и PIN.
