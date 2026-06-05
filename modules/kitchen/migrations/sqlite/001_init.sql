-- Kitchen Display System (KDS) · esquema inicial (SQLite). Portado de modules/m_kitchen/models.py.
-- Modelos: KitchenSettings (singleton por hub) + KitchenOrderLog (auditoría de acciones KDS).
-- Las órdenes/estaciones viven en el módulo `orders` (kitchen_orders_*); este módulo es la capa
-- de display/auditoría. Las FKs cruzadas NO se declaran aquí (tablas de otro módulo).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración de display por hub (singleton).
CREATE TABLE IF NOT EXISTS kitchen_settings (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    auto_accept_orders      INTEGER NOT NULL DEFAULT 0,
    show_timer              INTEGER NOT NULL DEFAULT 1,
    warning_time_minutes    INTEGER NOT NULL DEFAULT 15,
    critical_time_minutes   INTEGER NOT NULL DEFAULT 30,
    items_per_page          INTEGER NOT NULL DEFAULT 12,
    auto_refresh_seconds    INTEGER NOT NULL DEFAULT 3,
    sound_enabled           INTEGER NOT NULL DEFAULT 1,
    sound_on_new_order      INTEGER NOT NULL DEFAULT 1,
    sound_on_rush           INTEGER NOT NULL DEFAULT 1,
    auto_bump_enabled       INTEGER NOT NULL DEFAULT 0,
    auto_bump_delay_seconds INTEGER NOT NULL DEFAULT 5,
    color_coding_enabled    INTEGER NOT NULL DEFAULT 1,
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kitchen_settings_hub ON kitchen_settings (hub_id);
CREATE INDEX IF NOT EXISTS idx_kitchen_settings_hub ON kitchen_settings (hub_id, is_deleted);

-- Auditoría de acciones sobre órdenes en el KDS (recibida, aceptada, bumped, servida, cancelada…).
-- order_id/order_item_id/station_id referencian tablas del módulo `orders` (sin FK física aquí).
CREATE TABLE IF NOT EXISTS kitchen_order_log (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    order_item_id   TEXT,
    station_id      TEXT,
    action          TEXT NOT NULL,                 -- received|accepted|started|bumped|completed|served|recalled|cancelled|priority_changed|item_bumped
    performed_by_id TEXT,
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_kitchen_order_log_hub   ON kitchen_order_log (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS idx_kitchen_order_log_order ON kitchen_order_log (hub_id, order_id);
