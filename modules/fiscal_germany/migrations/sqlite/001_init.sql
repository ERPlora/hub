-- Fiscal Germany · esquema inicial (SQLite). Portado fielmente de old_modules/m_fiscal_germany/models.py.
-- Modelos: DeFiscalConfig (config fiscal alemana por hub), XRechnungDocument (factura electrónica
-- B2G UBL 2.1), ZUGFeRDDocument (factura híbrida PDF/A-3 + XML B2B) y GoBDAuditExport
-- (exportación de auditoría inmutable por periodo contable).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración fiscal alemana por hub: USt-IdNr (NIF-IVA), Steuernummer (nº fiscal
-- regional), nombre de empresa y Leitweg-ID por defecto para enrutado B2G de XRechnung.
-- ust_id es único por hub (una identidad fiscal por empresa).
CREATE TABLE IF NOT EXISTS fiscal_germany_config (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    ust_id                TEXT NOT NULL,                 -- NIF-IVA alemán: DE + 9 dígitos
    steuernummer          TEXT NOT NULL DEFAULT '',      -- nº fiscal regional (10-13 chars)
    company_name          TEXT NOT NULL,
    leitweg_id_default    TEXT NOT NULL DEFAULT '',      -- Leitweg-ID por defecto para B2G
    xrechnung_environment TEXT NOT NULL DEFAULT 'test',  -- test|production
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fiscal_de_hub_ust_id  ON fiscal_germany_config (hub_id, ust_id);
CREATE INDEX        IF NOT EXISTS idx_fiscal_germany_config_hub ON fiscal_germany_config (hub_id, is_deleted);

-- Documento XRechnung (factura electrónica B2G, UBL 2.1) enviada a destinatarios del
-- sector público vía Leitweg-ID. document_number autogenerado: XR-YYYYMMDD-NNNN.
-- status: draft|validated|submitted|accepted|rejected. validation_errors es JSON (lista) o NULL.
CREATE TABLE IF NOT EXISTS fiscal_germany_xrechnung (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    document_number     TEXT NOT NULL,
    invoice_ref         TEXT NOT NULL DEFAULT '',     -- referencia libre a la factura origen (sin FK)
    supplier_ust_id     TEXT NOT NULL,
    customer_leitweg_id TEXT NOT NULL,                -- Leitweg-ID del destinatario público
    total_netto         NUMERIC NOT NULL DEFAULT 0,
    total_steuer        NUMERIC NOT NULL DEFAULT 0,
    total_brutto        NUMERIC NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'draft',
    xml_content         TEXT NOT NULL DEFAULT '',     -- payload UBL 2.1 generado
    validation_errors   TEXT,                         -- JSON (lista de issues) o NULL
    submission_date     TEXT,                         -- ISO datetime o NULL
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_de_xr_hub_status  ON fiscal_germany_xrechnung (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_de_xr_hub_number  ON fiscal_germany_xrechnung (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_germany_xrechnung_hub ON fiscal_germany_xrechnung (hub_id, is_deleted);

-- Documento ZUGFeRD (factura híbrida PDF/A-3 con XML embebido) para B2B.
-- document_number autogenerado: ZF-YYYYMMDD-NNNN. profile: basic|comfort|extended.
CREATE TABLE IF NOT EXISTS fiscal_germany_zugferd (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    document_number TEXT NOT NULL,
    invoice_ref     TEXT NOT NULL DEFAULT '',
    supplier_ust_id TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    total_netto     NUMERIC NOT NULL DEFAULT 0,
    total_brutto    NUMERIC NOT NULL DEFAULT 0,
    profile         TEXT NOT NULL DEFAULT 'comfort',
    pdf_a3_path     TEXT NOT NULL DEFAULT '',         -- ruta al PDF/A-3 generado (S3 o local)
    xml_embedded    TEXT NOT NULL DEFAULT '',         -- XML embebido en el adjunto del PDF/A-3
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_de_zf_hub_profile ON fiscal_germany_zugferd (hub_id, profile);
CREATE INDEX IF NOT EXISTS ix_fiscal_de_zf_hub_number  ON fiscal_germany_zugferd (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_germany_zugferd_hub ON fiscal_germany_zugferd (hub_id, is_deleted);

-- Exportación de auditoría GoBD: paquete inmutable de contabilidad para un periodo cerrado.
-- Genera un ZIP (index.xml + CSV/JSON) destinado a inspectores fiscales.
CREATE TABLE IF NOT EXISTS fiscal_germany_gobd_export (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    period_start   TEXT NOT NULL,                     -- ISO YYYY-MM-DD
    period_end     TEXT NOT NULL,                     -- ISO YYYY-MM-DD
    generated_at   TEXT,                              -- ISO datetime o NULL
    total_records  INTEGER NOT NULL DEFAULT 0,
    audit_zip_path TEXT NOT NULL DEFAULT '',          -- ruta al ZIP GoBD generado
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_de_gobd_hub_period ON fiscal_germany_gobd_export (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_fiscal_germany_gobd_export_hub ON fiscal_germany_gobd_export (hub_id, is_deleted);
