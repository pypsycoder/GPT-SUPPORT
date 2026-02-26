Модуль `gpt_support` — заглушка под будущих LLM-агентов (GPT-поддержка).

Актуальная реализация LLM-слоя вынесена в `app/llm/`:

| Файл | Назначение |
|---|---|
| `app/llm/pool.py` | Пул аккаунтов GigaChat (AccountPool, GigaChatClient) |
| `app/llm/router.py` | Классификация запросов (RequestType, RouterResult) |
| `app/llm/agent.py` | Генерация ответов, сборка промптов |
| `app/llm/context_builder.py` | Сбор контекста пациента из БД |
| `app/llm/domain_scorer.py` | Числовая оценка доменов (sleep, routine, vitals, ...) |
| `app/llm/keywords.py` | Ключевые слова для классификации |
| `app/llm/parser.py` | Парсинг неструктурированного текста |
| `app/llm/anomaly.py` | Детектор аномалий витальных показателей |
| `app/llm/proactive.py` | Генератор проактивных сообщений |
| `app/llm/scheduler.py` | APScheduler: проактивные задания 08:00 / 14:00 / 20:00 |
| `app/llm/prompts/` | Системные промпты (base_system, domain_*, proactive_*) |

Сам модуль `gpt_support/` сейчас не используется в рабочем коде.
Планируется использовать для RAG-агентов и мультиагентной оркестрации (Roadmap).
