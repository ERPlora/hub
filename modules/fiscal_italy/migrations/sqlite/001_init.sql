-- Fiscal Italy · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_fiscal_italy/models.py.
-- Modelos: ItFiscalConfig (config fiscal por hub: Partita IVA + credenciales SdI),
-- FatturaPADocument (factura electrónica saliente vía SdI, XML 1.2),
-- EsterometroEntry (línea de transacción transfronteriza) y
-- EsterometroDeclaration (declaración mensual agregada del Esterometro).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración fiscal italiana por hub: Partita IVA, Codice Fiscale, entorno SdI.
-- partita_iva es única por hub (una identidad fiscal por empresa).
CREATE TABLE IF NOT EXISTS fiscal_italy_config (
    id                          TEXT PRIMARY KEY,
    hub_id                      TEXT NOT NULL,
    partita_iva                 TEXT NOT NULL,                       -- 11 dígitos numéricos
    codice_fiscale              TEXT NOT NULL,
    company_name                TEXT NOT NULL,
    sdi_environment             TEXT NOT NULL DEFAULT 'test',        -- test|production
    sdi_credentials_hash        TEXT NOT NULL DEFAULT '',            -- SHA256 hex (nunca en claro)
    default_codice_destinatario TEXT NOT NULL DEFAULT '0000000',     -- 7 chars
    is_deleted                  INTEGER NOT NULL DEFAULT 0,
    deleted_at                  TEXT,
    created_by                  TEXT,
    updated_by                  TEXT,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_fiscal_it_cfg_hub_piva ON fiscal_italy_config (hub_id, partita_iva);
CREATE INDEX        IF NOT EXISTS idx_fiscal_italy_config_hub ON fiscal_italy_config (hub_id, is_deleted);

-- Documento FatturaPA saliente entregado vía SdI (XML 1.2).
-- document_number autogenerado por hub y día: FPA-YYYYMMDD-NNNN.
CREATE TABLE IF NOT EXISTS fiscal_italy_fatturapa (
    id                            TEXT PRIMARY KEY,
    hub_id                        TEXT NOT NULL,
    document_number               TEXT NOT NULL,
    invoice_ref                   TEXT NOT NULL DEFAULT '',          -- ref libre a la factura origen (sin FK)
    supplier_piva                 TEXT NOT NULL,
    customer_piva                 TEXT NOT NULL,
    customer_codice_destinatario  TEXT NOT NULL DEFAULT '0000000',   -- 7 chars; 0000000 = B2C/desconocido
    total_imponibile              NUMERIC NOT NULL DEFAULT 0,
    total_iva                     NUMERIC NOT NULL DEFAULT 0,
    total_documento               NUMERIC NOT NULL DEFAULT 0,
    status                        TEXT NOT NULL DEFAULT 'draft',     -- draft|uploaded|delivered|rejected|accepted
    xml_content                   TEXT NOT NULL DEFAULT '',          -- payload XML FatturaPA 1.2
    sdi_id                        TEXT NOT NULL DEFAULT '',          -- IdentificativoSdI devuelto tras upload
    submission_date               TEXT,                              -- ISO datetime o NULL
    rejection_reason              TEXT NOT NULL DEFAULT '',          -- motivo de rechazo del SdI
    is_deleted                    INTEGER NOT NULL DEFAULT 0,
    deleted_at                    TEXT,
    created_by                    TEXT,
    updated_by                    TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_it_fpa_hub_status  ON fiscal_italy_fatturapa (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_it_fpa_hub_number  ON fiscal_italy_fatturapa (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_italy_fatturapa_hub ON fiscal_italy_fatturapa (hub_id, is_deleted);

-- Línea de transacción transfronteriza registrada para el Esterometro.
-- transaction_type: sale (saliente/attivo) o purchase (entrante/passivo).
CREATE TABLE IF NOT EXISTS fiscal_italy_esterometro_entry (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    period_year           INTEGER NOT NULL,
    period_month          INTEGER NOT NULL,
    transaction_type      TEXT NOT NULL,                             -- sale|purchase
    counterparty_country  TEXT NOT NULL,                             -- ISO 3166-1 alpha-2
    counterparty_vat_id   TEXT NOT NULL,
    total_amount          NUMERIC NOT NULL DEFAULT 0,
    transaction_date      TEXT NOT NULL,                             -- ISO YYYY-MM-DD
    document_ref          TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'pending',           -- pending|included|submitted
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_it_estr_entry_hub_period ON fiscal_italy_esterometro_entry (hub_id, period_year, period_month);
CREATE INDEX IF NOT EXISTS ix_fiscal_it_estr_entry_hub_status ON fiscal_italy_esterometro_entry (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_fiscal_italy_esterometro_entry_hub ON fiscal_italy_esterometro_entry (hub_id, is_deleted);

-- Declaración mensual del Esterometro que agrega las líneas transfronterizas.
-- Única por (hub, period_year, period_month).
CREATE TABLE IF NOT EXISTS fiscal_italy_esterometro_declaration (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    period_year         INTEGER NOT NULL,
    period_month        INTEGER NOT NULL,
    total_entries       INTEGER NOT NULL DEFAULT 0,
    submitted_at        TEXT,                                        -- ISO datetime o NULL
    submission_status   TEXT NOT NULL DEFAULT 'draft',              -- draft|generated|submitted
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_fiscal_it_estr_decl_period ON fiscal_italy_esterometro_declaration (hub_id, period_year, period_month);
CREATE INDEX        IF NOT EXISTS ix_fiscal_it_estr_decl_hub_period ON fiscal_italy_esterometro_declaration (hub_id, period_year, period_month);
CREATE INDEX        IF NOT EXISTS idx_fiscal_italy_esterometro_declaration_hub ON fiscal_italy_esterometro_declaration (hub_id, is_deleted);
