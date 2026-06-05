-- Rules & Triggers · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_rules_triggers/models.py.
-- Modelos: Trigger (fuente de evento), Rule (condición→acción, opcionalmente ligada a un
-- trigger) y RuleEvaluation (auditoría de cada evaluación del motor de reglas).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Trigger: fuente de evento que dispara la evaluación de reglas.
-- event_type ∈ entity_created|entity_updated|entity_deleted|scheduled|webhook.
-- entity_filter acota (p.ej. "customers.customer"). code es único por hub.
-- last_fired_at / fire_count son contadores de uso (los actualiza el motor en runtime).
CREATE TABLE IF NOT EXISTS rules_triggers_trigger (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    event_type    TEXT NOT NULL DEFAULT 'entity_created',  -- entity_created|entity_updated|entity_deleted|scheduled|webhook
    entity_filter TEXT NOT NULL DEFAULT '',                -- p.ej. "customers.customer", '' = cualquiera
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_fired_at TEXT,                                    -- ISO datetime o NULL
    fire_count    INTEGER NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_rt_trg_hub_code   ON rules_triggers_trigger (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_rt_trg_hub_event  ON rules_triggers_trigger (hub_id, event_type);
CREATE INDEX        IF NOT EXISTS ix_rt_trg_hub_active ON rules_triggers_trigger (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_rules_triggers_trigger_hub ON rules_triggers_trigger (hub_id, is_deleted);

-- Rule: definición condición→acción, opcionalmente ligada a un trigger.
-- conditions/actions son JSON ([{field,op,value}] y [{type,params}]). Se evalúan por
-- priority ascendente (menor = corre primero). stop_on_match corta la cadena al matchear.
-- total_evaluations / total_matches son contadores que actualiza el motor en runtime.
CREATE TABLE IF NOT EXISTS rules_triggers_rule (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    code              TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    trigger_id        TEXT,                          -- FK trigger (NULL = regla sin trigger)
    priority          INTEGER NOT NULL DEFAULT 100,
    conditions        TEXT NOT NULL DEFAULT '[]',    -- JSON [{field,op,value}]
    actions           TEXT NOT NULL DEFAULT '[]',    -- JSON [{type,params}]
    stop_on_match     INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1,
    total_evaluations INTEGER NOT NULL DEFAULT 0,
    total_matches     INTEGER NOT NULL DEFAULT 0,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (trigger_id) REFERENCES rules_triggers_trigger (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_rt_rule_hub_code     ON rules_triggers_rule (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_rt_rule_hub_active   ON rules_triggers_rule (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS ix_rt_rule_hub_trigger  ON rules_triggers_rule (hub_id, trigger_id);
CREATE INDEX        IF NOT EXISTS ix_rt_rule_hub_priority ON rules_triggers_rule (hub_id, priority);
CREATE INDEX        IF NOT EXISTS idx_rules_triggers_rule_hub ON rules_triggers_rule (hub_id, is_deleted);

-- RuleEvaluation: registro de auditoría de una única evaluación de regla.
-- matched indica si las condiciones se cumplieron; output guarda las acciones ejecutadas.
-- input_data/output son JSON. Las escribe el motor de evaluación (handler WASM).
CREATE TABLE IF NOT EXISTS rules_triggers_evaluation (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    rule_id           TEXT NOT NULL,
    trigger_id        TEXT,                          -- FK trigger (NULL si evaluación sin trigger)
    evaluated_at      TEXT,                          -- ISO datetime o NULL
    matched           INTEGER NOT NULL DEFAULT 0,
    input_data        TEXT NOT NULL DEFAULT '{}',    -- JSON payload evaluado
    output            TEXT NOT NULL DEFAULT '{}',    -- JSON {actions_executed:[...]}
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (rule_id)    REFERENCES rules_triggers_rule (id)    ON DELETE CASCADE,
    FOREIGN KEY (trigger_id) REFERENCES rules_triggers_trigger (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_rt_eval_hub_rule         ON rules_triggers_evaluation (hub_id, rule_id);
CREATE INDEX IF NOT EXISTS ix_rt_eval_hub_matched      ON rules_triggers_evaluation (hub_id, matched);
CREATE INDEX IF NOT EXISTS ix_rt_eval_hub_evaluated_at ON rules_triggers_evaluation (hub_id, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_rules_triggers_evaluation_hub ON rules_triggers_evaluation (hub_id, is_deleted);
