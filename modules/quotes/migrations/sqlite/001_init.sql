-- Quotes · esquema inicial (SQLite). Portado fielmente de old_modules/m_quotes/models.py.
-- Modelos: Quote, QuoteLine, QuoteCounter.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cotización al cliente (oferta con líneas y flujo de estado).
CREATE TABLE IF NOT EXISTS quotes_quote (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    quote_number      TEXT NOT NULL,                       -- Q-YYYYMMDD-NNNN (counter atómico)
    customer_name     TEXT NOT NULL,
    customer_email    TEXT NOT NULL DEFAULT '',
    customer_tax_id   TEXT NOT NULL DEFAULT '',
    issue_date        TEXT NOT NULL,                       -- ISO date
    valid_until       TEXT,                                -- ISO date | NULL
    status            TEXT NOT NULL DEFAULT 'draft',       -- draft|sent|accepted|rejected|expired|converted
    total_amount      NUMERIC NOT NULL DEFAULT 0,          -- bruto (impuesto incluido)
    tax_amount        NUMERIC NOT NULL DEFAULT 0,          -- IVA extraído del bruto
    notes             TEXT NOT NULL DEFAULT '',
    terms_conditions  TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);
CREATE INDEX        IF NOT EXISTS idx_quotes_quote_hub          ON quotes_quote (hub_id, is_deleted);
CREATE INDEX        IF NOT EXISTS ix_quotes_hub_status          ON quotes_quote (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_quotes_hub_issue_date      ON quotes_quote (hub_id, issue_date);
CREATE INDEX        IF NOT EXISTS ix_quotes_hub_valid_until     ON quotes_quote (hub_id, valid_until);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quote_hub_number           ON quotes_quote (hub_id, quote_number);

-- Línea de cotización (descripción + cantidad + precio + impuesto).
CREATE TABLE IF NOT EXISTS quotes_quote_line (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    quote_id      TEXT NOT NULL,
    description   TEXT NOT NULL,
    quantity      NUMERIC NOT NULL DEFAULT 1,
    unit_price    NUMERIC NOT NULL,
    discount_pct  NUMERIC NOT NULL DEFAULT 0,
    tax_rate      NUMERIC NOT NULL DEFAULT 0,
    line_total    NUMERIC NOT NULL DEFAULT 0,              -- bruto = qty*unit*(1-discount)
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (quote_id) REFERENCES quotes_quote (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_quotes_quote_line_hub   ON quotes_quote_line (hub_id, is_deleted);
CREATE INDEX IF NOT EXISTS ix_quotes_line_quote        ON quotes_quote_line (hub_id, quote_id);

-- Contador atómico por (hub, día) para generar quote_number sin carrera.
CREATE TABLE IF NOT EXISTS quotes_quote_counter (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    day          TEXT NOT NULL,                            -- YYYYMMDD
    last_number  INTEGER NOT NULL DEFAULT 0,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE INDEX        IF NOT EXISTS idx_quotes_quote_counter_hub  ON quotes_quote_counter (hub_id, is_deleted);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quote_counter_hub_day      ON quotes_quote_counter (hub_id, day);
