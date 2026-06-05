-- Lots & Serials · esquema inicial (SQLite). Portado fielmente de old_modules/m_lots_serials/models.py.
-- Modelos: Lot (lote/batch de producción con cantidad inicial y actual), SerialNumber (unidad
-- individual con ciclo de vida in_stock→sold→returned/scrapped, opcionalmente ligada a un lote) y
-- LotMovement (movimiento de cantidad firmado aplicado a un lote: intake/consume/adjust/expire/recall).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Lote / batch de producción rastreado para trazabilidad.
-- lot_number es único por hub. product_ref es una referencia libre (no FK a inventory: el módulo
-- puede funcionar standalone). status: active|expired|recalled|depleted.
CREATE TABLE IF NOT EXISTS lots_serials_lot (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    lot_number        TEXT NOT NULL,
    product_ref       TEXT NOT NULL,
    manufactured_date TEXT,                          -- ISO YYYY-MM-DD o NULL
    expiry_date       TEXT,                          -- ISO YYYY-MM-DD o NULL
    quantity_initial  NUMERIC NOT NULL DEFAULT 0,
    quantity_current  NUMERIC NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'active', -- active|expired|recalled|depleted
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_lot_hub_number      ON lots_serials_lot (hub_id, lot_number);
CREATE INDEX        IF NOT EXISTS ix_lot_hub_product     ON lots_serials_lot (hub_id, product_ref);
CREATE INDEX        IF NOT EXISTS ix_lot_hub_status      ON lots_serials_lot (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_lot_hub_expiry      ON lots_serials_lot (hub_id, expiry_date);
CREATE INDEX        IF NOT EXISTS idx_lots_serials_lot_hub ON lots_serials_lot (hub_id, is_deleted);

-- Número de serie: una unidad única, opcionalmente ligada a un lote padre.
-- serial es único por hub. status: in_stock|sold|returned|scrapped.
CREATE TABLE IF NOT EXISTS lots_serials_serial (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    serial               TEXT NOT NULL,
    product_ref          TEXT NOT NULL,
    lot_id               TEXT,                        -- FK opcional a lots_serials_lot (SET NULL)
    status               TEXT NOT NULL DEFAULT 'in_stock', -- in_stock|sold|returned|scrapped
    current_location_ref TEXT NOT NULL DEFAULT '',
    sold_at              TEXT,                         -- ISO datetime o NULL (se rellena al vender)
    sold_to_customer     TEXT NOT NULL DEFAULT '',
    notes                TEXT NOT NULL DEFAULT '',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (lot_id) REFERENCES lots_serials_lot (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_serial_hub_serial      ON lots_serials_serial (hub_id, serial);
CREATE INDEX        IF NOT EXISTS ix_serial_hub_product     ON lots_serials_serial (hub_id, product_ref);
CREATE INDEX        IF NOT EXISTS ix_serial_hub_status      ON lots_serials_serial (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_serial_hub_lot         ON lots_serials_serial (hub_id, lot_id);
CREATE INDEX        IF NOT EXISTS idx_lots_serials_serial_hub ON lots_serials_serial (hub_id, is_deleted);

-- Movimiento de cantidad aplicado a un lote. quantity_delta es firmado: positivo para intake /
-- adjust positivo, negativo para consume/expire/recall. La capa de servicio aplica el delta a
-- Lot.quantity_current (eso va a runtime/WASM). occurred_at es independiente de created_at para
-- permitir movimientos retroactivos importados.
CREATE TABLE IF NOT EXISTS lots_serials_movement (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    lot_id         TEXT NOT NULL,
    movement_type  TEXT NOT NULL,                     -- intake|consume|adjust|expire|recall
    quantity_delta NUMERIC NOT NULL DEFAULT 0,
    reference      TEXT NOT NULL DEFAULT '',          -- ref libre (sale ID, PO, ticket de recall)
    occurred_at    TEXT NOT NULL,                     -- ISO datetime del movimiento
    notes          TEXT NOT NULL DEFAULT '',
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (lot_id) REFERENCES lots_serials_lot (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_movement_hub_lot          ON lots_serials_movement (hub_id, lot_id);
CREATE INDEX IF NOT EXISTS ix_movement_hub_type         ON lots_serials_movement (hub_id, movement_type);
CREATE INDEX IF NOT EXISTS idx_lots_serials_movement_hub ON lots_serials_movement (hub_id, is_deleted);
