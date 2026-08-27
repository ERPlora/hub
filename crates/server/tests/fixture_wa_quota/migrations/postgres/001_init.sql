-- Singleton de ajustes del canal. Del módulo real solo se conservan las columnas que esta
-- sincronización toca o que el `ON CONFLICT` necesita; `greeting` está a propósito para poder
-- comprobar que una escritura de cuota NO pisa lo que es del comerciante.
CREATE TABLE IF NOT EXISTS whatsapp_inbox_settings (
  id                      TEXT PRIMARY KEY,
  hub_id                  TEXT NOT NULL,
  free_tier_monthly_limit INTEGER NOT NULL DEFAULT 0,
  greeting                TEXT NOT NULL DEFAULT '',
  is_deleted              INTEGER NOT NULL DEFAULT 0,
  created_by              TEXT,
  updated_by              TEXT,
  created_at              TEXT,
  updated_at              TEXT
);

-- El índice al que apunta el `ON CONFLICT(hub_id)` del command.
CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_inbox_settings_hub
  ON whatsapp_inbox_settings (hub_id);
