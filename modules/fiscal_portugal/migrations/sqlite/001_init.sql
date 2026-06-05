-- Fiscal Portugal · esquema inicial (SQLite). Portado fielmente de old_modules/m_fiscal_portugal/models.py.
-- Modelos: PtFiscalConfig (config fiscal por hub: NIF + entorno AT + códigos de certificación),
-- SAFTExport (export SAF-T PT periódico), ATCUDDocument (código ATCUD por documento emitido)
-- y ATCommunication (Comunicação à AT: faturas / transporte / inventario).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración fiscal portuguesa por hub: NIF (9 dígitos), entorno AT y códigos de
-- certificación de serie/software. NUNCA se persisten credenciales AT en claro: solo el
-- hash SHA256. nif es único por hub (una identidad fiscal por empresa).
CREATE TABLE IF NOT EXISTS fiscal_portugal_config (
    id                            TEXT PRIMARY KEY,
    hub_id                        TEXT NOT NULL,
    nif                           TEXT NOT NULL,                       -- NIF portugués, 9 dígitos
    company_name                  TEXT NOT NULL,
    at_environment                TEXT NOT NULL DEFAULT 'test',        -- test|production
    at_credentials_hash           TEXT NOT NULL DEFAULT '',            -- SHA256 hex de las credenciales AT
    serie_certification_code      TEXT NOT NULL DEFAULT '',            -- código de certificación de serie (segmento inicial del ATCUD)
    software_certification_number TEXT NOT NULL DEFAULT '',            -- nº de certificación del software emitido por AT
    is_deleted                    INTEGER NOT NULL DEFAULT 0,
    deleted_at                    TEXT,
    created_by                    TEXT,
    updated_by                    TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fiscal_pt_hub_nif       ON fiscal_portugal_config (hub_id, nif);
CREATE INDEX        IF NOT EXISTS idx_fiscal_portugal_config_hub ON fiscal_portugal_config (hub_id, is_deleted);

-- Export SAF-T PT periódico (mensual / anual / auditoría). document_number autogenerado
-- por hub y día: SAFT-YYYYMMDD-NNNN. xml_content guarda el payload XML generado (TEXT).
CREATE TABLE IF NOT EXISTS fiscal_portugal_saft (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    document_number TEXT NOT NULL,                       -- SAFT-YYYYMMDD-NNNN
    period_start    TEXT NOT NULL,                        -- ISO YYYY-MM-DD
    period_end      TEXT NOT NULL,                        -- ISO YYYY-MM-DD
    period_type     TEXT NOT NULL DEFAULT 'monthly',      -- monthly|yearly|audit
    xml_content     TEXT NOT NULL DEFAULT '',
    total_invoices  INTEGER NOT NULL DEFAULT 0,
    total_amount    NUMERIC NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'draft',        -- draft|generated|submitted
    generated_at    TEXT,
    submitted_at    TEXT,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_saft_hub_status  ON fiscal_portugal_saft (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_saft_hub_period  ON fiscal_portugal_saft (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_saft_hub_number  ON fiscal_portugal_saft (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_portugal_saft_hub  ON fiscal_portugal_saft (hub_id, is_deleted);

-- Código ATCUD asignado a un documento emitido (factura / nota de crédito / recibo).
-- Formato ATCUD: <serie_cert>-<seq>. hash_value/hash_method encadenan el documento con el
-- anterior (exigencia del software de facturación certificado portugués).
CREATE TABLE IF NOT EXISTS fiscal_portugal_atcud (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    document_type        TEXT NOT NULL DEFAULT 'invoice',   -- invoice|credit_note|receipt
    document_series_code TEXT NOT NULL,                      -- código de serie emitido por AT
    document_number      TEXT NOT NULL,
    atcud                TEXT NOT NULL,                       -- <serie_cert>-<seq>
    invoice_ref          TEXT NOT NULL DEFAULT '',            -- referencia libre a la factura origen (sin FK)
    hash_value           TEXT NOT NULL DEFAULT '',            -- hash del documento (encadenado)
    hash_method          TEXT NOT NULL DEFAULT 'SHA1',
    signed               INTEGER NOT NULL DEFAULT 0,
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_atcud_hub_type   ON fiscal_portugal_atcud (hub_id, document_type);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_atcud_hub_atcud  ON fiscal_portugal_atcud (hub_id, atcud);
CREATE INDEX IF NOT EXISTS idx_fiscal_portugal_atcud_hub ON fiscal_portugal_atcud (hub_id, is_deleted);

-- Comunicação à AT (faturas / transporte / inventario). document_number autogenerado por
-- hub y día: ATC-YYYYMMDD-NNNN. submission_id es el identificador devuelto por AT tras enviar.
CREATE TABLE IF NOT EXISTS fiscal_portugal_at_comm (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    document_number    TEXT NOT NULL,                      -- ATC-YYYYMMDD-NNNN
    communication_type TEXT NOT NULL DEFAULT 'invoice',    -- invoice|transport|inventory
    reference_period   TEXT NOT NULL,                       -- YYYY-MM | YYYY | rango libre
    content_xml        TEXT NOT NULL DEFAULT '',
    submission_id      TEXT NOT NULL DEFAULT '',            -- id devuelto por AT
    status             TEXT NOT NULL DEFAULT 'draft',       -- draft|submitted|accepted|rejected
    submitted_at       TEXT,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_atcomm_hub_status ON fiscal_portugal_at_comm (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_fiscal_pt_atcomm_hub_number ON fiscal_portugal_at_comm (hub_id, document_number);
CREATE INDEX IF NOT EXISTS idx_fiscal_portugal_at_comm_hub ON fiscal_portugal_at_comm (hub_id, is_deleted);
