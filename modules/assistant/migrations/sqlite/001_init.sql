-- Assistant · esquema inicial (SQLite). Portado de old_modules/m_assistant/models.py.
-- Modelos: AssistantConversation (estado de conversación por usuario/contexto),
-- AssistantMessage (historial local de chat — fuente de verdad del render) y
-- AssistantActionLog (auditoría de cada tool ejecutada por el asistente, con
-- confirmación pendiente/confirmada para el bucle agéntico).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
--
-- NOTA: este es un módulo de sistema (is_system) cuya inteligencia (proxy LLM,
-- bucle agéntico, tools tipadas, RAG) vive en el runtime/Cloud, NO en SQL. Aquí
-- sólo se modela la PERSISTENCIA de conversaciones/mensajes/logs. Ver WASM-TODO.md.

-- Conversación: una sesión de chat de un usuario en un contexto (general|setup|...).
-- openai_response_id es el cursor opaco del proveedor LLM (lo gestiona el proxy de Cloud).
CREATE TABLE IF NOT EXISTS assistant_conversation (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    openai_response_id TEXT NOT NULL DEFAULT '',
    context            TEXT NOT NULL DEFAULT 'general',
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS ix_assistant_conv_hub_user ON assistant_conversation (hub_id, created_by);
CREATE INDEX IF NOT EXISTS ix_assistant_conv_hub_ctx  ON assistant_conversation (hub_id, context);
CREATE INDEX IF NOT EXISTS idx_assistant_conversation_hub ON assistant_conversation (hub_id, is_deleted);

-- Mensaje de chat: texto visible (role=user|assistant|system). Los tool calls y sus
-- resultados NO se duplican aquí; viven en assistant_action_log.
CREATE TABLE IF NOT EXISTS assistant_message (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (conversation_id) REFERENCES assistant_conversation (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_assistant_msg_hub_conv_created ON assistant_message (hub_id, conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_assistant_message_hub ON assistant_message (hub_id, is_deleted);

-- Log de acción: auditoría de una tool ejecutada por el asistente. confirmed/success
-- modelan el flujo de confirmación previa a mutaciones (ver WASM-TODO §confirm/cancel).
-- tool_args/result son JSON serializado como TEXT (SQLite no tiene JSONB).
-- openai_call_id reanuda el bucle agéntico tras confirmar (function_call_output).
CREATE TABLE IF NOT EXISTS assistant_action_log (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    conversation_id TEXT,
    tool_name       TEXT NOT NULL,
    tool_args       TEXT NOT NULL DEFAULT '{}',
    result          TEXT NOT NULL DEFAULT '{}',
    success         INTEGER NOT NULL DEFAULT 0,
    confirmed       INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT NOT NULL DEFAULT '',
    openai_call_id  TEXT,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (conversation_id) REFERENCES assistant_conversation (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_assistant_log_hub_user ON assistant_action_log (hub_id, created_by);
CREATE INDEX IF NOT EXISTS ix_assistant_log_tool     ON assistant_action_log (hub_id, tool_name);
CREATE INDEX IF NOT EXISTS idx_assistant_action_log_hub ON assistant_action_log (hub_id, is_deleted);
