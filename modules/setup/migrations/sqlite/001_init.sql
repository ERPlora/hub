-- Setup · esquema inicial (SQLite). Portado de modules/m_setup/models.py.
-- Modelo único: SetupState — fila singleton por hub que rastrea el progreso del
-- asistente de primer arranque (onboarding). Flujo de status:
--   pending → in_progress → completed
--                        ↘ skipped
--                        ↘ error
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- NOTA: este módulo es meta (orquesta otros módulos). La lógica de apply_template
-- (instalar módulos, sembrar IVA/categorías/productos) vive en WASM — ver WASM-TODO.md.
-- Este módulo OWNea solo la tabla setup_state; NO toca tablas de otros módulos.

CREATE TABLE IF NOT EXISTS setup_state (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending|in_progress|completed|skipped|error
    template_key  TEXT NOT NULL DEFAULT '',         -- clave de la plantilla de sector aplicada
    answers       TEXT NOT NULL DEFAULT '{}',       -- JSON con las respuestas del wizard
    error_message TEXT NOT NULL DEFAULT '',         -- mensaje del último fallo (truncado a 500)
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
-- Singleton por hub: un único estado de setup vigente por hub.
CREATE UNIQUE INDEX IF NOT EXISTS ix_setup_state_hub    ON setup_state (hub_id, is_deleted);
CREATE INDEX        IF NOT EXISTS idx_setup_state_hub   ON setup_state (hub_id, is_deleted);
