-- Память агентной системы. PostgreSQL 14+, расширение vector (pgvector).
-- Схема отдельная, чтобы не смешивать с доменными данными.
--
-- Четыре слоя, четыре разных срока жизни и четыре разных способа чтения:
--   agent_turn      — сырой лог ходов (append-only, источник истины)
--   agent_summary   — эпизодическая память: свёртки ходов
--   agent_fact      — семантическая память: устойчивые факты о пациенте (key-value)
--   agent_call_log  — телеметрия вызовов LLM (деньги, кэш, латентность)
--
-- Принцип: сырой лог никогда не идёт в промпт целиком. В промпт идут
-- summary + факты + хвост окна. Лог нужен для пересборки и разборов.

CREATE SCHEMA IF NOT EXISTS agent;
CREATE EXTENSION IF NOT EXISTS vector;

-- --------------------------------------------------------------------------
-- 0. Диалоговый тред
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent.thread (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      INTEGER NOT NULL REFERENCES users.users(id),
    -- Стабильный ключ кэша GigaChat: передаётся в X-Session-ID.
    session_key     TEXT    NOT NULL,
    -- Отпечаток стабильной части промпта. Смена = кэш обнулён осознанно.
    prefix_fp       TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'active',   -- active | closed
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_thread_patient_active
    ON agent.thread (patient_id, status, last_active_at DESC);

-- --------------------------------------------------------------------------
-- 1. WORKING MEMORY — сырой лог ходов
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent.turn (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id     UUID    NOT NULL REFERENCES agent.thread(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,                    -- порядковый номер в треде
    role          TEXT    NOT NULL,                    -- user | assistant | function
    content       TEXT    NOT NULL,
    -- Для ассистентских ходов с функциями
    function_call JSONB,
    functions_state_id TEXT,
    -- Признак вытеснения из активного окна в summary
    compacted     BOOLEAN NOT NULL DEFAULT FALSE,
    tokens        INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thread_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_turn_window
    ON agent.turn (thread_id, compacted, seq DESC);

-- --------------------------------------------------------------------------
-- 2. EPISODIC MEMORY — свёртки
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent.summary (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id     UUID    NOT NULL REFERENCES agent.thread(id) ON DELETE CASCADE,
    -- Диапазон свёрнутых ходов: позволяет пересобрать при смене промпта свёртки
    seq_from      INTEGER NOT NULL,
    seq_to        INTEGER NOT NULL,
    text          TEXT    NOT NULL,
    tokens        INTEGER NOT NULL DEFAULT 0,
    -- Версия промпта сумматора: при обновлении можно пересчитать старые свёртки
    summarizer_version TEXT NOT NULL DEFAULT 'v1',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_summary_thread ON agent.summary (thread_id, seq_to DESC);

-- --------------------------------------------------------------------------
-- 3. SEMANTIC MEMORY — устойчивые факты о пациенте
-- --------------------------------------------------------------------------
-- Пишется ТОЛЬКО через memory-gate, никогда напрямую из специалиста.
-- Ключ нормализован: один key = один активный факт (UPSERT по (patient_id, key)).
CREATE TABLE IF NOT EXISTS agent.fact (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id     INTEGER NOT NULL REFERENCES users.users(id),
    key            TEXT    NOT NULL,
    value          JSONB   NOT NULL,
    -- Почему записали. Только из белого списка политик.
    policy         TEXT    NOT NULL,      -- explicit_user_preference | repeated_pattern |
                                          -- progress_event | stable_behavior_signal
    confidence     REAL    NOT NULL DEFAULT 0.5,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    evidence       JSONB   NOT NULL DEFAULT '[]'::jsonb,  -- короткие цитаты-обоснования
    -- Срок годности: факты про самочувствие протухают, предпочтения нет
    expires_at     TIMESTAMPTZ,
    status         TEXT    NOT NULL DEFAULT 'active',     -- active | superseded | retracted
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_active
    ON agent.fact (patient_id, key) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS ix_fact_patient ON agent.fact (patient_id, status);

-- История изменений фактов: нужна для аудита и для отката плохих записей.
CREATE TABLE IF NOT EXISTS agent.fact_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id     UUID NOT NULL,
    patient_id  INTEGER NOT NULL,
    key         TEXT NOT NULL,
    old_value   JSONB,
    new_value   JSONB,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- 4. RETRIEVAL MEMORY — векторный индекс контента
-- --------------------------------------------------------------------------
-- 1024 — под EmbeddingsGigaR. Уточните размерность своей модели и поправьте.
CREATE TABLE IF NOT EXISTS agent.chunk (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_kind  TEXT NOT NULL,          -- lesson | practice | faq | protocol
    source_id    TEXT NOT NULL,
    title        TEXT NOT NULL,
    text         TEXT NOT NULL,
    tokens       INTEGER NOT NULL DEFAULT 0,
    embedding    vector(1024),
    -- Лексический поиск для гибридной выдачи
    tsv          tsvector GENERATED ALWAYS AS
                 (to_tsvector('russian', coalesce(title,'') || ' ' || coalesce(text,''))) STORED,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chunk_vec
    ON agent.chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_chunk_tsv
    ON agent.chunk USING gin (tsv);

-- --------------------------------------------------------------------------
-- 5. ТЕЛЕМЕТРИЯ — без неё оптимизировать нечего
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent.call_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id     UUID,
    patient_id    INTEGER,
    step          TEXT NOT NULL,           -- router | agent | summarizer | judge | tool
    model         TEXT NOT NULL,
    session_key   TEXT,
    prefix_fp     TEXT,
    prompt_tokens        INTEGER NOT NULL DEFAULT 0,
    completion_tokens    INTEGER NOT NULL DEFAULT 0,
    precached_tokens     INTEGER NOT NULL DEFAULT 0,
    total_tokens         INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    finish_reason TEXT,
    ok            BOOLEAN NOT NULL DEFAULT TRUE,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_call_log_time ON agent.call_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_call_log_thread ON agent.call_log (thread_id, created_at);

-- Дежурный запрос «работает ли кэш»:
--   SELECT date_trunc('hour', created_at) AS h,
--          sum(precached_tokens)::float / nullif(sum(prompt_tokens + precached_tokens),0) AS hit,
--          sum(total_tokens) AS billed
--   FROM agent.call_log
--   WHERE created_at > now() - interval '2 days'
--   GROUP BY 1 ORDER BY 1;
