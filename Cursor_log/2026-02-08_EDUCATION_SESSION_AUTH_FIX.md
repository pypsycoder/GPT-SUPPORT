**Задача:** Исправление тестов после прохождения урока — переход на сессионную аутентификацию

**Дата:** 2026-02-08

**Проблема:**
После внедрения сессионной аутентификации (вместо передачи patient_token в теле запроса) тесты к урокам перестали работать. Фронтенд отправлял `patient_token` в body запроса, который API больше не ожидал.

**Действия:**

### 1. Фиксы фронтенда (education-модуль)

#### `frontend/patient/education_test.html`
- ✅ Удален `patient_token` из payload в функции `submitTestAnswers()`
- ✅ Добавлен `credentials: 'include'` во все fetch запросы:
  - `fetchLessonTest()` → GET /lessons/{lesson_code}/test
  - `fetchTestQuestions()` → GET /tests/{test_id}/questions
  - `submitTestAnswers()` → POST /tests/{test_id}/submit

#### `frontend/patient/education.html`
- ✅ Добавлен `credentials: 'include'` во все fetch запросы:
  - `markLessonAsRead()` → POST /lessons/{lesson_code}/mark_read
  - `loadLessonTestInfo()` → GET /lessons/{lesson_code}/test
  - Загрузка списка уроков → GET /lessons
  - Загрузка карточек урока → GET /lessons/{lesson_code}/cards

#### `frontend/patient/education_overview.html`
- ✅ Добавлен `credentials: 'include'` в fetch запрос:
  - `loadEducationBlocks()` → GET /api/v1/education/lessons/overview

**Файлы изменены:**
- `frontend/patient/education_test.html` (удаление patient_token, добавление credentials)
- `frontend/patient/education.html` (добавление credentials во все fetch)
- `frontend/patient/education_overview.html` (добавление credentials)

**Технические детали:**
- `credentials: 'include'` гарантирует передачу сессионного HttpOnly cookie с каждым запросом
- Это позволяет `get_current_user` в API получать аутентифицированного пользователя из session-токена
- Токены больше НЕ передаются в URL или в теле запроса (улучшение безопасности)

**Результат:** 
✅ Тесты к урокам теперь полностью совместимы с сессионной аутентификацией
✅ Безопасность: HttpOnly cookies не доступны из JavaScript (защита от XSS)
✅ Обработка результатов тестов: LessonTestResult корректно сохраняется с `user.patient_token` из сессии

**Как проверить:**
1. Войти через PIN (создаётся сессионный токен)
2. Перейти в раздел "Занятия"
3. Выбрать урок и нажать "Пройти тест"
4. Ответить на вопросы и нажать "Завершить"
5. Результат должен сохраниться в БД без ошибок
6. Проверить в `education.lesson_test_results` что запись создана с правильным `patient_token`

**Проблемы:** Нет
