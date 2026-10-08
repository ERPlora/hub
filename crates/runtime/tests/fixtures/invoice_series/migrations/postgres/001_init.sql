-- Invoice_series · esquema inicial (Postgres / Aurora cloud). Equivalente a
-- migrations/sqlite/001_init.sql — mismas tablas, índices, FK y contrato de fila del
-- hub (§2.5): hub_id + soft-delete + auditoría. Generado por paridad mecánica.
--
-- Tipos: subconjunto portable "ERPlora SQL" (ADR-0007):
--   * ids/refs → TEXT (UUIDs del runtime como texto);
--   * flags 0/1 → INTEGER (los commands bindean 0/1; Postgres no castea entero→bool);
--   * importes → NUMERIC;
--   * FECHAS → TEXT ISO-8601 (NO TIMESTAMPTZ): el motor de sync (ADR-0031) compara
--     updated_at como string lexicográfico; timestamptz rompería el LWW entre dialectos.

CREATE TABLE IF NOT EXISTS invoice_series_series (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    document_type    TEXT NOT NULL DEFAULT 'invoice',                 -- invoice|credit_note|proforma|receipt|quote
    prefix           TEXT NOT NULL DEFAULT '',
    suffix           TEXT NOT NULL DEFAULT '',
    format           TEXT NOT NULL DEFAULT '{prefix}-{year}-{seq:05d}',
    country_code     TEXT NOT NULL DEFAULT '',                        -- ISO-2
    region_code      TEXT NOT NULL DEFAULT '',
    fiscal_year      INTEGER NOT NULL,
    current_sequence INTEGER NOT NULL DEFAULT 0,                      -- estado de la secuencia (lo avanza el handler WASM atómico)
    is_default       INTEGER NOT NULL DEFAULT 0,
    is_active        INTEGER NOT NULL DEFAULT 1,
    start_date       TEXT,                                            -- ventana de validez (ISO date)
    end_date         TEXT,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT,
    updated_at       TEXT
);
-- code único por hub (uq_invoice_series_hub_code en el legacy; aquí filtramos is_deleted=0 vía índice parcial).
CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_series_hub_code   ON invoice_series_series (hub_id, code) WHERE is_deleted = 0;
CREATE INDEX        IF NOT EXISTS ix_invoice_series_hub_doc     ON invoice_series_series (hub_id, document_type);
CREATE INDEX        IF NOT EXISTS ix_invoice_series_hub_country ON invoice_series_series (hub_id, country_code);
CREATE INDEX        IF NOT EXISTS ix_invoice_series_hub         ON invoice_series_series (hub_id, is_deleted);

-- Auditoría: una fila por cada número entregado por get_next_number (RD 1007/2023: sin huecos, sin duplicados).
-- (series_id, document_number) es único — un duplicado señala un bug de cumplimiento grave.
CREATE TABLE IF NOT EXISTS invoice_series_allocation (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    series_id        TEXT NOT NULL,
    document_number  TEXT NOT NULL,
    document_ref     TEXT NOT NULL DEFAULT '',
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT,
    updated_at       TEXT,
    FOREIGN KEY (series_id) REFERENCES invoice_series_series (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_series_allocation_number ON invoice_series_allocation (series_id, document_number);
CREATE INDEX        IF NOT EXISTS ix_invoice_series_alloc_series ON invoice_series_allocation (series_id);
CREATE INDEX        IF NOT EXISTS ix_invoice_series_alloc_hub    ON invoice_series_allocation (hub_id, is_deleted);