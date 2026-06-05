-- AI Setup Wizard · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_ai_setup_wizard/models.py.
-- Modelos: SetupSession (una sesión de onboarding guiada por IA), SetupQuestion
-- (turno de pregunta ordenado dentro de la sesión) y SetupRecommendation
-- (recomendación accionable emitida por la IA atada a una sesión).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Las columnas JSON (goals, pain_points, options, ...) se almacenan como TEXT con JSON.

-- Sesión de onboarding: una ejecución guiada por IA iniciada por un operador.
-- session_number tiene formato SET-YYYYMMDD-NNNN (secuencia por hub+día).
CREATE TABLE IF NOT EXISTS ai_setup_wizard_session (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    session_number       TEXT NOT NULL,
    business_type        TEXT NOT NULL,
    industry_description TEXT NOT NULL DEFAULT '',
    goals                TEXT NOT NULL DEFAULT '[]',   -- JSON array de strings
    pain_points          TEXT NOT NULL DEFAULT '[]',   -- JSON array de strings
    team_size            INTEGER NOT NULL DEFAULT 1,
    status               TEXT NOT NULL DEFAULT 'active', -- active|abandoned|completed
    started_at           TEXT,
    completed_at         TEXT,
    recommended_modules  TEXT NOT NULL DEFAULT '[]',   -- JSON array de module ids
    applied_modules      TEXT NOT NULL DEFAULT '[]',   -- JSON array de module ids
    user_ref             TEXT,                         -- UUID suelto del operador (no FK)
    notes                TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS ix_ai_setup_session_hub_status ON ai_setup_wizard_session (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_ai_setup_session_hub_user   ON ai_setup_wizard_session (hub_id, user_ref);
CREATE INDEX IF NOT EXISTS ix_ai_setup_session_hub_number ON ai_setup_wizard_session (hub_id, session_number);
CREATE INDEX IF NOT EXISTS idx_ai_setup_wizard_session_hub ON ai_setup_wizard_session (hub_id, is_deleted);

-- Turno de pregunta ordenado dentro de una sesión.
-- question_order es 1-based por sesión. options es JSON (para single/multi_choice).
CREATE TABLE IF NOT EXISTS ai_setup_wizard_question (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    question_order INTEGER NOT NULL DEFAULT 0,
    question_type  TEXT NOT NULL DEFAULT 'text', -- text|single_choice|multi_choice|scale
    question_text  TEXT NOT NULL,
    options        TEXT NOT NULL DEFAULT '[]',   -- JSON array de opciones
    answer         TEXT NOT NULL DEFAULT '',
    answered_at    TEXT,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (session_id) REFERENCES ai_setup_wizard_session (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ai_setup_question_session    ON ai_setup_wizard_question (session_id, question_order);
CREATE INDEX IF NOT EXISTS idx_ai_setup_wizard_question_hub ON ai_setup_wizard_question (hub_id, is_deleted);

-- Recomendación accionable emitida por la IA atada a una sesión.
-- category: modules|integrations|workflows|config. priority: low|medium|high.
-- related_module_id apunta (opcional) a un módulo del marketplace (string, no FK).
CREATE TABLE IF NOT EXISTS ai_setup_wizard_recommendation (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    category          TEXT NOT NULL DEFAULT 'modules',
    title             TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    priority          TEXT NOT NULL DEFAULT 'medium',
    is_applied        INTEGER NOT NULL DEFAULT 0,
    applied_at        TEXT,
    related_module_id TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (session_id) REFERENCES ai_setup_wizard_session (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_ai_setup_reco_session_category ON ai_setup_wizard_recommendation (session_id, category);
CREATE INDEX IF NOT EXISTS ix_ai_setup_reco_session_applied  ON ai_setup_wizard_recommendation (session_id, is_applied);
CREATE INDEX IF NOT EXISTS idx_ai_setup_wizard_recommendation_hub ON ai_setup_wizard_recommendation (hub_id, is_deleted);
