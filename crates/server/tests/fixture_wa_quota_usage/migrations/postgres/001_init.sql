-- Same singleton as `fixture_wa_quota`, plus the column whatsapp_inbox#155 adds: the spend the
-- platform reports. `greeting` is here for the same reason as next door — to prove a quota write
-- does not trample what belongs to the merchant.
CREATE TABLE IF NOT EXISTS whatsapp_inbox_settings (
  id                      TEXT PRIMARY KEY,
  hub_id                  TEXT NOT NULL,
  free_tier_monthly_limit INTEGER NOT NULL DEFAULT 0,
  monthly_usage           INTEGER NOT NULL DEFAULT 0,
  greeting                TEXT NOT NULL DEFAULT '',
  is_deleted              INTEGER NOT NULL DEFAULT 0,
  created_by              TEXT,
  updated_by              TEXT,
  created_at              TEXT,
  updated_at              TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_inbox_settings_hub
  ON whatsapp_inbox_settings (hub_id);
