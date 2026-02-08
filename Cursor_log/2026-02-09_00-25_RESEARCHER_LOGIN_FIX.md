**Задача:** Исправить логин исследователя — после ввода корректных данных страница перезагружалась вместо перехода на dashboard

**Дата:** 2026-02-09 00:25

**Действия:**
- Диагностирован баг: endpoint `/api/v1/auth/researcher/me` возвращал 500 Internal Server Error
- Корневая причина: зомби-процессы Uvicorn с `--reload` на Windows не перезагружались и обслуживали запросы со сломанным кодом (содержавшим незавершённую debug-инструментацию из предыдущих попыток)
- Убита вся инструментация, мешавшая работе бэкенда
- Добавлен `credentials: 'include'` во все fetch-запросы фронтенда (auth.js, patients.js)
- Добавлен CORSMiddleware в `app/main.py`
- Очищен код от всей debug-инструментации после подтверждения работоспособности

**Файлы:**
- `frontend/researcher/js/auth.js` (очищен от инструментации)
- `frontend/researcher/dashboard.html` (очищен от инструментации)
- `frontend/researcher/login.html` (убран cache-busting)
- `app/main.py` (убран debug exception handler)
- `app/auth/dependencies.py` (очищен от инструментации)
- `app/auth/session_crud.py` (очищен от инструментации)
- `app/auth/router.py` (восстановлен оригинальный endpoint researcher_me)

**Результат:** Логин исследователя работает корректно. Login → cookie → dashboard → requireAuth → 200 OK.

**Проблемы:** Uvicorn `--reload` на Windows создаёт зомби-процессы, которые продолжают обслуживать запросы со старым кодом. Рекомендуется убивать все python.exe перед перезапуском.
