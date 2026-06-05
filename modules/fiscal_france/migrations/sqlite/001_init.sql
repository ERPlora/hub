-- Fiscal France · esquema inicial (SQLite). Portado fielmente de old_modules/m_fiscal_france/models.py.
-- Modelos: FrFiscalConfig (config fiscal por hub: SIRET/SIREN + entorno Chorus Pro),
-- FacturXDocument (factura Factur-X: PDF/A-3 con XML ZUGFeRD/UN-CEFACT incrustado),
-- ChorusInvoice (factura B2G enviada al portal Chorus Pro) y
-- FECExport (export del Fichier des Écritures Comptables exigido por la DGFiP).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración fiscal francesa por hub. Una sola fila por hub en la práctica.
-- siret es único por hub (una identidad fiscal por empresa) — lo garantiza el índice.
CREATE TABLE IF NOT EXISTS fiscal_france_config (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    siret                   TEXT NOT NULL,                       -- 14 dígitos (establecimiento)
    siren                   TEXT NOT NULL,                       -- 9 dígitos (empresa)
    company_name            TEXT NOT NULL,
    chorus_pro_environment  TEXT NOT NULL DEFAULT 'qualif',      -- qualif|production
    chorus_credentials_hash TEXT NOT NULL DEFAULT '',            -- SHA256 hex, nunca credenciales en claro
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_fiscal_fr_cfg_hub_siret ON fiscal_france_config (hub_id, siret);
CREATE INDEX        IF NOT EXISTS idx_fiscal_france_config_hub ON fiscal_france_config (hub_id, is_deleted);

-- Factura Factur-X (PDF/A-3 híbrido + XML UN/CEFACT ZUGFeRD incrustado).
-- document_number autogenerado por hub+día: FX-YYYYMMDD-NNNN.
CREATE TABLE IF NOT EXISTS fiscal_france_facturx (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    document_number     TEXT NOT NULL,
    invoice_ref         TEXT NOT NULL DEFAULT '',                -- ref libre a la factura origen (sin FK)
    supplier_siret      TEXT NOT NULL,
    customer_siret      TEXT NOT NULL,
    total_amount_ht     NUMERIC NOT NULL DEFAULT 0,              -- base imponible
    vat_amount          NUMERIC NOT NULL DEFAULT 0,              -- IVA
    total_amount_ttc    NUMERIC NOT NULL DEFAULT 0,              -- total con impuestos (ht + vat)
    status              TEXT NOT NULL DEFAULT 'draft',           -- draft|generated|submitted|validated
    pdf_a3_content      BLOB,                                    -- PDF/A-3 incrustado (real puede ir a S3)
    xml_zugferd_content TEXT NOT NULL DEFAULT '',                -- XML Cross-Industry Invoice generado
    submission_date     TEXT,                                    -- ISO datetime o NULL
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_fr_facturx_hub_status ON fiscal_france_facturx (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_fr_facturx_hub_number ON fiscal_france_facturx (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_france_facturx_hub   ON fiscal_france_facturx (hub_id, is_deleted);

-- Factura Chorus Pro (envío B2G al portal del sector público francés).
-- document_number autogenerado por hub+día: CPI-YYYYMMDD-NNNN.
CREATE TABLE IF NOT EXISTS fiscal_france_chorus (
    id                     TEXT PRIMARY KEY,
    hub_id                 TEXT NOT NULL,
    document_number        TEXT NOT NULL,
    invoice_ref            TEXT NOT NULL DEFAULT '',             -- ref libre a la factura origen
    recipient_service_code TEXT NOT NULL,                        -- código de servicio Chorus Pro de la entidad pública
    total_amount           NUMERIC NOT NULL DEFAULT 0,
    status                 TEXT NOT NULL DEFAULT 'draft',        -- draft|uploaded|under_review|accepted|rejected|paid
    upload_id              TEXT NOT NULL DEFAULT '',             -- identificador devuelto por Chorus Pro tras subida
    anomaly_code           TEXT NOT NULL DEFAULT '',             -- código de anomalía si rechazada
    is_deleted             INTEGER NOT NULL DEFAULT 0,
    deleted_at             TEXT,
    created_by             TEXT,
    updated_by             TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_fr_chorus_hub_status ON fiscal_france_chorus (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_fr_chorus_hub_number ON fiscal_france_chorus (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_france_chorus_hub   ON fiscal_france_chorus (hub_id, is_deleted);

-- Export FEC (Fichier des Écritures Comptables) — fichero de auditoría obligatorio (DGFiP).
-- Solo se persisten los metadatos; el payload (CSV/XML) se devuelve inline al generar.
CREATE TABLE IF NOT EXISTS fiscal_france_fec (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    period_start  TEXT NOT NULL,                                 -- ISO YYYY-MM-DD
    period_end    TEXT NOT NULL,                                 -- ISO YYYY-MM-DD
    format_type   TEXT NOT NULL DEFAULT 'csv',                   -- csv|xml
    generated_at  TEXT,                                          -- ISO datetime o NULL
    total_entries INTEGER NOT NULL DEFAULT 0,                    -- nº de asientos serializados
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_fr_fec_hub_period ON fiscal_france_fec (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_fiscal_france_fec_hub   ON fiscal_france_fec (hub_id, is_deleted);
