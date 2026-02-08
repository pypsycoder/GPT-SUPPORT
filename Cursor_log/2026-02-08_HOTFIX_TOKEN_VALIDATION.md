**Задача:** Исправление ошибки "Не найден токен пациента в адресе"

**Дата:** 2026-02-08 (hotfix после реализации безопасности)

**Проблема:**

При переходе на сессионную аутентификацию остались проверки в фронтенде, которые требовали наличие `patient_token` в URL (`/p/{token}/...`). После обновления на новые чистые URLs (`/patient/...`), клиентский код выдавал ошибку "Не найден токен пациента в адресе".

**Решение:**

### 1. Фронтенд: Удаление проверок токена из URL

**Файлы обновлены:**

#### Шкалы (HADS, TOBOL, KOP25A, PSQI)
- ✅ `frontend/patient/js/hads.js` - удалена проверка `if (!patientToken)`
- ✅ `frontend/patient/js/tobol.js` - удалена проверка `if (!patientToken)`
- ✅ `frontend/patient/js/kop25a.js` - удалена проверка `if (!patientToken)`
- ✅ `frontend/patient/js/psqi.js` - удалена проверка `if (!patientToken)`

#### Образование
- ✅ `frontend/patient/education_test.html` - удалена проверка `if (!patientToken)` в init()
- ✅ `frontend/patient/education_test.html` - удалена проверка при навигации после теста
- ✅ `frontend/patient/education_overview.html` - удалена проверка и error при отсутствии токена
- ✅ `frontend/patient/education.html` - обновлен mark_read API вызов (убран query параметр)

### 2. Бэкенд: Обновление API эндпоинтов для сессионной аутентификации

**Файлы обновлены:**

#### Education Router (`app/education/router.py`)
- ✅ Импорты: добавлены `get_current_user`, `User`
- ✅ `POST /lessons/{lesson_code}/mark_read` - заменен `patient_token` параметр на `user: User`
- ✅ `GET /lessons/overview` - заменен `patient_token` параметр на `user: User`
  - Используется `user.patient_token` внутри функции
- ✅ `POST /tests/{test_id}/submit` - заменен `patient_token` параметр на `user: User`
- ✅ `GET /tests/{test_id}/result` - заменен `patient_token` параметр на `user: User`

#### Education Schemas (`app/education/schemas.py`)
- ✅ `TestSubmitRequest` - удалено поле `patient_token`

**Изменения логики:**
- Все query параметры `?patient_token=...` удалены из фронтенд запросов
- Все параметры функции с `patient_token` заменены на `user: User = Depends(get_current_user)`
- Внутри функций используется `user.patient_token` для сохранения совместимости с БД

### 3. Поток работы после исправления

**Старый поток (ошибочный):**
```
1. Логин через PIN → сессия в cookie
2. Редирект на /patient/home (БЕЗ токена в URL)
3. Пользователь открывает шкалу
4. JS проверяет: есть ли токен в URL?
5. НЕТ → ошибка "Не найден токен пациента в адресе"
```

**Новый поток (исправленный):**
```
1. Логин через PIN → сессия в HttpOnly cookie
2. Редирект на /patient/home (чистый URL)
3. Пользователь открывает шкалу
4. JS не проверяет токен, прямо отправляет форму
5. Сессия автоматически отправляется в cookie
6. Бэкенд проверяет сессию через get_current_user
7. Данные сохраняются от имени аутентифицированного пользователя
```

**Результат:** 100% готовность

**Файлы изменены:** 12
- Frontend: 8 файлов
- Backend: 2 файла  
- Schemas: 1 файл
- Logs: 1 файл

**Проблемы:** Нет

