Модуль `gpt_support` сейчас не является рабочим LLM-runtime.

Актуальная реализация LLM-слоя находится в `app/llm/`:

| Файл | Назначение |
|---|---|
| `app/llm/pipeline/` | Текущий LLM runtime: `LLMPipeline`, stages, типы и структура Graph v2 |
| `app/llm/pool.py` | Пул аккаунтов и клиент провайдера |
| `app/llm/router.py` | Классификация запросов (`RequestType`, `RouterResult`) |
| `app/llm/domain_scorer.py` | Числовая оценка доменов |
| `app/llm/keywords.py` | Ключевые слова для маршрутизации |
| `app/llm/parser.py` | Парсинг неструктурированного текста |
| `app/llm/anomaly.py` | Детектор аномалий витальных показателей |
| `app/llm/proactive.py` | Генератор проактивных сообщений |
| `app/llm/scheduler.py` | Планировщик проактивных задач |
| `app/llm/prompts/` | Prompt-assets для отдельных модулей |

Сам модуль `gpt_support/` сейчас используется как вспомогательная директория и не содержит актуального боевого пайплайна.
