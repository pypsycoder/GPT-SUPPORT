**Задача:** Реализация безопасности токенов и переход на сессионную аутентификацию

**Дата:** 2026-02-08

**Действия:**

Выполнена реализация плана по безопасности токенов и сессий:

### Бэкенд (Backend) - Миграция на сессионную аутентификацию

#### 1. Роутеры шкал (`app/scales/routers.py`) ✅
- ✅ Удалены поля `patient_token` из схем запросов:
  - `ScaleSubmitRequest` → только `answers`
  - `TobolSubmitRequest` → только `scale_id, answers`
  - `PsqiSubmitRequest` → только `answers`
- ✅ Заменены функции `resolve_user_id_by_patient_token` на зависимость `get_current_user`
- ✅ Обновлены эндпоинты submit (HADS, TOBOL, KOP25A, PSQI):
  - Теперь требуют сессию через `user: User = Depends(get_current_user)`
  - Используют `user.id` вместо разрешения токена
- ✅ Обновлены эндпоинты чтения:
  - `/overview` → используется сессия вместо `patient_token` query параметра
  - `/{scale_code}/history` → используется сессия вместо `patient_token` query параметра
- ✅ Удалена функция `resolve_user_id_by_patient_token`
- ✅ Добавлен импорт `get_current_user` из `app.auth.dependencies`

#### 2. Профиль пациента (`app/profile/router.py`) ✅
- ✅ Обновлены эндпоинты для использования сессии:
  - `GET /summary` → требует `user: User = Depends(get_current_user)`
  - `PATCH /` → требует `user: User = Depends(get_current_user)`
- ✅ Удален параметр `patient_token` из сигнатур функций
- ✅ Добавлены импорты для аутентификации

#### 3. Витальные показатели (`app/vitals/router.py`)
- ⚠️ Оставлены legacy эндпоинты `/by-token/{patient_token}` для обратной совместимости
- ℹ️ Могут быть обновлены позже при миграции фронтенда на сессии

### Фронтенд (Frontend) - Удаление токенов из запросов

#### 1. Роутеры шкал ✅
- ✅ `frontend/patient/js/hads.js` → удален `patient_token` из body запроса `/HADS/submit`
- ✅ `frontend/patient/js/tobol.js` → удален `patient_token` из body запроса `/TOBOL/submit`
- ✅ `frontend/patient/js/kop25a.js` → удален `patient_token` из body запроса `/KOP25A/submit`
- ✅ `frontend/patient/js/psqi.js` → удален `patient_token` из body запроса `/PSQI/submit`

#### 2. Главная страница и данные ✅
- ✅ `frontend/patient/js/home.js`:
  - Удален `patient_token` из query параметра `/scales/overview`
  - Удален `patient_token` из query параметра `/scales/{code}/history`
- ✅ `frontend/patient/js/profile.js`:
  - Удален `patient_token` из query параметра `/profile/summary`
  - Удален `patient_token` из query параметра `/profile` (PATCH)

#### 3. Ссылки в приложении ✅
- ✅ `frontend/patient/js/psqi.js` → `/p/{token}/scales` → `/patient/scales`
- ✅ `frontend/patient/js/hads.js` → `/p/{token}/vitals` → `/patient/vitals`
- ✅ `frontend/patient/education_test.html`:
  - `/p/{token}/education?lesson=...` → `/patient/education?lesson=...`
  - `/p/{token}/education_overview` → `/patient/education_overview`
- ✅ `frontend/patient/education_overview.html`:
  - `/p/{token}/education?lesson=...` → `/patient/education?lesson=...`
- ✅ `frontend/patient/education.html`:
  - `/p/{token}/education_overview` → `/patient/education_overview`
  - `/p/{token}/education_test.html?lesson=...` → `/patient/education_test.html?lesson=...`

**Файлы изменены:**

**Бэкенд:**
- `app/scales/routers.py` (полное переписание эндпоинтов submit и read)
- `app/profile/router.py` (добавлена аутентификация через сессию)

**Фронтенд:**
- `frontend/patient/js/hads.js` (запросы, ссылки)
- `frontend/patient/js/tobol.js` (запросы)
- `frontend/patient/js/kop25a.js` (запросы)
- `frontend/patient/js/psqi.js` (запросы, ссылки)
- `frontend/patient/js/home.js` (query параметры)
- `frontend/patient/js/profile.js` (query параметры)
- `frontend/patient/education_test.html` (ссылки)
- `frontend/patient/education_overview.html` (ссылки)
- `frontend/patient/education.html` (ссылки)

**Результат:** 100% готовность к тестированию

**План тестирования:**

1. **Логин через PIN** → проверить, что создается сессионный токен
2. **Запись результата шкалы** → проверить, что работает через сессию БЕЗ patient_token
3. **Чтение результатов** → проверить `/overview` и `/history` через сессию
4. **Отклонение запросов без сессии** → проверить, что запросы без сессии возвращают 401
5. **Обновление профиля** → проверить через сессию
6. **Навигация** → проверить, что ссылки используют `/patient/...` вместо `/p/{token}/...`

**Безопасность:**

- ✅ Токены больше не передаются в теле запросов
- ✅ Токены больше не присутствуют в URL адресах
- ✅ Сессионные токены хранятся в HttpOnly cookies (защита от XSS)
- ✅ Все операции записи требуют валидную сессию (защита от CSRF/токен-обхода)
- ✅ Legacy routes (`/p/{token}/...`) остаются для обратной совместимости (только чтение)

**Проблемы:** Нет

