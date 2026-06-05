-- Collections · esquema inicial (SQLite). Portado fielmente de old_modules/m_collections/models.py.
-- Modelos: Collection (cobro entrante), CollectionAllocation (reparto del cobro contra facturas)
-- y CollectionCounter (secuencia atómica por hub+día para la referencia COL-YYYYMMDD-NNNN).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cobro entrante (transferencia/tarjeta/efectivo/sepa/otro) recibido por el hub.
-- Nace en estado 'pending'; al asignarse por completo a facturas pasa a 'allocated'.
-- reference es único por hub (COL-YYYYMMDD-NNNN). payer_name/payer_iban son texto libre:
-- el módulo NO referencia con FK a ningún CRM ni al módulo de facturación (independiente).
CREATE TABLE IF NOT EXISTS collections_collection (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    reference       TEXT NOT NULL,                  -- COL-YYYYMMDD-NNNN, único por hub
    collection_date TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    amount          NUMERIC NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'EUR',
    payer_name      TEXT NOT NULL,
    payer_iban      TEXT NOT NULL DEFAULT '',
    concept         TEXT NOT NULL DEFAULT '',
    method          TEXT NOT NULL DEFAULT 'transfer', -- transfer|card|cash|sepa|other
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|allocated|refunded|cancelled
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_hub_reference ON collections_collection (hub_id, reference);
CREATE INDEX        IF NOT EXISTS ix_collection_hub_status    ON collections_collection (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_collection_hub_date      ON collections_collection (hub_id, collection_date);
CREATE INDEX        IF NOT EXISTS ix_collection_hub_payer     ON collections_collection (hub_id, payer_name);
CREATE INDEX        IF NOT EXISTS idx_collections_collection_hub ON collections_collection (hub_id, is_deleted);

-- Reparto de una porción del cobro contra una factura concreta. invoice_ref es texto
-- libre (normalmente el nº de factura) para no exigir el módulo invoice instalado.
-- La suma de amount_allocated nunca debe superar el amount del cobro (invariant → WASM).
CREATE TABLE IF NOT EXISTS collections_allocation (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    collection_id    TEXT NOT NULL,
    invoice_ref      TEXT NOT NULL,
    amount_allocated NUMERIC NOT NULL,
    allocated_at     TEXT NOT NULL,                 -- ISO datetime
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (collection_id) REFERENCES collections_collection (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_alloc_hub_collection      ON collections_allocation (hub_id, collection_id);
CREATE INDEX IF NOT EXISTS ix_alloc_hub_invoice_ref     ON collections_allocation (hub_id, invoice_ref);
CREATE INDEX IF NOT EXISTS idx_collections_allocation_hub ON collections_allocation (hub_id, is_deleted);

-- Contador atómico por (hub, día) para generar la referencia del cobro sin carrera
-- SELECT→UPDATE. Se escribe vía UPSERT (INSERT ... ON CONFLICT DO UPDATE ... RETURNING).
-- En hub-next el incremento lo realiza el runtime/WASM; esta tabla guarda el estado.
CREATE TABLE IF NOT EXISTS collections_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                      -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_counter_hub_day ON collections_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_collections_counter_hub   ON collections_counter (hub_id, is_deleted);
