# local_models/

Локальный, не пушится в Git (см. `.gitignore`).

Сюда кладутся веса ONNX-моделей для локального теста через `onnxruntime`
(например, антисуицидальная/crisis-модель — альтернатива embedding-запросам
к GigaChat в `app/llm/crisis_semantic.py`, см. `LLM_CRISIS_SEMANTIC`).

Файлы весов (`*.onnx`) в этой папке не отслеживаются git — держите их
только локально.
