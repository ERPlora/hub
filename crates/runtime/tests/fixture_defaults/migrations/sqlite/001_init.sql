-- Columna `status` y `priority` son NOT NULL **sin DEFAULT de columna**: si el binder no
-- inyecta el `default` del JSON Schema cuando el caller omite la clave, el INSERT peta con
-- `NOT NULL constraint failed`. Es el caso exacto de la causa raíz (decision-log 2026-06-25),
-- aquí SIN el parche COALESCE que los módulos reales usan hoy.
CREATE TABLE IF NOT EXISTS defaults_item (
  id        TEXT PRIMARY KEY,
  hub_id    TEXT NOT NULL,
  name      TEXT NOT NULL,
  status    TEXT NOT NULL,
  priority  INTEGER NOT NULL
);
