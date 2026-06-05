-- Fiscal Romania · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_fiscal_romania/models.py.
-- Modelos: RoFiscalConfig (config fiscal por hub: CIF + entorno ANAF),
-- EFacturaDocument (factura electrónica saliente UBL 2.1 hacia ANAF),
-- ETransportDocument (aviso de transporte de mercancías / código UIT) y
-- JPKDeclaration (declaración periódica D300/D394/D406/SAFT).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración fiscal rumana (una por hub): identidad fiscal de la empresa,
-- entorno ANAF (test|production) y hash de la API key (nunca en claro).
CREATE TABLE IF NOT EXISTS fiscal_romania_config (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    company_cif           TEXT NOT NULL,           -- código IVA rumano: RO<digitos>
    company_name          TEXT NOT NULL,
    anaf_environment      TEXT NOT NULL DEFAULT 'test',   -- test|production
    api_key_hash          TEXT NOT NULL DEFAULT '',       -- SHA256 hex, nunca en claro
    last_token_refresh_at TEXT,                    -- ISO datetime del último refresh OAuth
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
-- CIF único por hub (una sola identidad fiscal por empresa).
CREATE UNIQUE INDEX IF NOT EXISTS ix_fiscal_ro_cfg_hub_cif ON fiscal_romania_config (hub_id, company_cif);
CREATE INDEX        IF NOT EXISTS idx_fiscal_romania_config_hub ON fiscal_romania_config (hub_id, is_deleted);

-- e-Factura: factura electrónica saliente (RO_CIUS / UBL 2.1) enviada a ANAF.
-- document_number autogenerado por hub y día: EFR-YYYYMMDD-NNNN.
CREATE TABLE IF NOT EXISTS fiscal_romania_efactura (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    document_number TEXT NOT NULL,
    invoice_ref     TEXT NOT NULL DEFAULT '',      -- referencia libre a la factura origen (sin FK)
    document_type   TEXT NOT NULL DEFAULT 'invoice', -- invoice|credit_note
    xml_content     TEXT NOT NULL DEFAULT '',      -- payload UBL 2.1 generado
    supplier_cif    TEXT NOT NULL,
    customer_cif    TEXT NOT NULL,
    total_amount    NUMERIC NOT NULL DEFAULT 0,
    vat_amount      NUMERIC NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'draft', -- draft|uploaded|validated|rejected
    upload_id       TEXT NOT NULL DEFAULT '',      -- identificador de subida ANAF
    submission_date TEXT,                          -- ISO datetime del envío
    anaf_response   TEXT,                          -- JSON con la respuesta de ANAF
    error_code      TEXT NOT NULL DEFAULT '',      -- código de error si rechazada
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_ro_efact_hub_status   ON fiscal_romania_efactura (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_ro_efact_hub_number   ON fiscal_romania_efactura (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_romania_efactura_hub ON fiscal_romania_efactura (hub_id, is_deleted);

-- e-Transport: aviso de transporte de mercancías monitorizado por ANAF.
-- document_number autogenerado por hub y día: ETR-YYYYMMDD-NNNN.
CREATE TABLE IF NOT EXISTS fiscal_romania_etransport (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    document_number  TEXT NOT NULL,
    transport_type   TEXT NOT NULL DEFAULT 'national', -- intra_eu|national|international
    origin_city      TEXT NOT NULL,
    destination_city TEXT NOT NULL,
    vehicle_plate    TEXT NOT NULL,
    departure_date   TEXT,                         -- ISO YYYY-MM-DD o NULL
    goods            TEXT,                          -- JSON: lista de mercancías transportadas
    uit_code         TEXT NOT NULL DEFAULT '',     -- código de tránsito devuelto por ANAF
    status           TEXT NOT NULL DEFAULT 'draft', -- draft|submitted|validated|cancelled
    submitted_at     TEXT,                          -- ISO datetime del envío
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_ro_etr_hub_status      ON fiscal_romania_etransport (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_ro_etr_hub_number      ON fiscal_romania_etransport (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_romania_etransport_hub ON fiscal_romania_etransport (hub_id, is_deleted);

-- JPK: declaración periódica (D300 IVA, D394 informativa, D406 SAFT, SAFT).
CREATE TABLE IF NOT EXISTS fiscal_romania_jpk (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    declaration_type TEXT NOT NULL,                -- D300|D394|D406|SAFT
    period_start     TEXT NOT NULL,                -- ISO YYYY-MM-DD
    period_end       TEXT NOT NULL,                -- ISO YYYY-MM-DD
    status           TEXT NOT NULL DEFAULT 'draft', -- draft|generated|submitted
    xml_content      TEXT NOT NULL DEFAULT '',
    total_amount     NUMERIC NOT NULL DEFAULT 0,
    submitted_at     TEXT,                          -- ISO datetime del envío
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_ro_jpk_hub_type   ON fiscal_romania_jpk (hub_id, declaration_type);
CREATE INDEX IF NOT EXISTS ix_fiscal_ro_jpk_hub_period ON fiscal_romania_jpk (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_fiscal_romania_jpk_hub  ON fiscal_romania_jpk (hub_id, is_deleted);
