-- SEPA Remittances · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_sepa_remittances/models.py.
-- Modelos: SepaMandate (autorización firmada del deudor), Remittance (lote de pagos
-- agrupado en un fichero XML pain.008/pain.001), RemittanceLine (adeudo/transferencia
-- individual) y RemittanceCounter (secuencia atómica por hub+día para SEPA-YYYYMMDD-NNNN).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Mandato SEPA: autorización firmada por un deudor (esquema CORE/B2B) usada por las
-- remesas de adeudo directo. mandate_id (UMR) es único por hub.
CREATE TABLE IF NOT EXISTS sepa_remittances_mandate (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    mandate_id   TEXT NOT NULL,                 -- referencia visible (UMR), única por hub
    debtor_name  TEXT NOT NULL,
    debtor_iban  TEXT NOT NULL,
    debtor_bic   TEXT NOT NULL DEFAULT '',
    creditor_id  TEXT NOT NULL,                 -- identificador del acreedor (CIF / SEPA Creditor Id)
    signed_date  TEXT,                          -- ISO YYYY-MM-DD o NULL
    status       TEXT NOT NULL DEFAULT 'active', -- active|revoked|expired
    revoked_at   TEXT,                          -- ISO timestamp o NULL
    scheme       TEXT NOT NULL DEFAULT 'CORE',  -- CORE|B2B
    notes        TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sepa_mandate_hub_mandate_id ON sepa_remittances_mandate (hub_id, mandate_id);
CREATE INDEX        IF NOT EXISTS ix_sepa_mandate_hub_status     ON sepa_remittances_mandate (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_sepa_mandate_hub_debtor     ON sepa_remittances_mandate (hub_id, debtor_name);
CREATE INDEX        IF NOT EXISTS idx_sepa_remittances_mandate_hub ON sepa_remittances_mandate (hub_id, is_deleted);

-- Remesa: lote de pagos SEPA agrupados en un único fichero XML.
-- remittance_id se autogenera por hub: SEPA-YYYYMMDD-NNNN (ver contador más abajo).
CREATE TABLE IF NOT EXISTS sepa_remittances_remittance (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    remittance_id   TEXT NOT NULL,                  -- SEPA-YYYYMMDD-NNNN, único por hub
    remittance_type TEXT NOT NULL,                  -- direct_debit|credit_transfer
    execution_date  TEXT NOT NULL,                  -- ISO YYYY-MM-DD
    total_amount    NUMERIC NOT NULL DEFAULT 0,
    total_count     INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'EUR',
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft|generated|sent|processed|rejected
    xml_content     TEXT NOT NULL DEFAULT '',       -- payload pain.008/pain.001 generado
    generated_at    TEXT,                           -- ISO timestamp o NULL
    sent_at         TEXT,                           -- ISO timestamp o NULL
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sepa_remittance_hub_remittance_id ON sepa_remittances_remittance (hub_id, remittance_id);
CREATE INDEX        IF NOT EXISTS ix_sepa_remittance_hub_status        ON sepa_remittances_remittance (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_sepa_remittance_hub_type          ON sepa_remittances_remittance (hub_id, remittance_type);
CREATE INDEX        IF NOT EXISTS ix_sepa_remittance_hub_date          ON sepa_remittances_remittance (hub_id, execution_date);
CREATE INDEX        IF NOT EXISTS idx_sepa_remittances_remittance_hub  ON sepa_remittances_remittance (hub_id, is_deleted);

-- Línea de remesa: adeudo/transferencia individual dentro del lote.
-- mandate_id solo aplica a líneas de adeudo directo (NULL en transferencias).
CREATE TABLE IF NOT EXISTS sepa_remittances_line (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    remittance_id     TEXT NOT NULL,                  -- FK a sepa_remittances_remittance.id
    mandate_id        TEXT,                           -- FK a sepa_remittances_mandate.id (NULL en credit_transfer)
    counterparty_name TEXT NOT NULL,
    counterparty_iban TEXT NOT NULL,
    amount            NUMERIC NOT NULL DEFAULT 0,
    concept           TEXT NOT NULL DEFAULT '',
    end_to_end_id     TEXT NOT NULL DEFAULT '',       -- identificador end-to-end (max 35) propagado al banco
    status            TEXT NOT NULL DEFAULT 'pending', -- pending|processed|rejected
    rejection_reason  TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (remittance_id) REFERENCES sepa_remittances_remittance (id) ON DELETE CASCADE,
    FOREIGN KEY (mandate_id)    REFERENCES sepa_remittances_mandate (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_sepa_line_remittance     ON sepa_remittances_line (remittance_id);
CREATE INDEX IF NOT EXISTS ix_sepa_line_mandate        ON sepa_remittances_line (mandate_id);
CREATE INDEX IF NOT EXISTS idx_sepa_remittances_line_hub ON sepa_remittances_line (hub_id, is_deleted);

-- Contador atómico por (hub, día) para la referencia remittance_id.
-- Se escribe vía upsert (INSERT ... ON CONFLICT DO UPDATE ... RETURNING) — sin ventana
-- de carrera SELECT/UPDATE. Capacidad del runtime, invocada desde el handler WASM.
CREATE TABLE IF NOT EXISTS sepa_remittances_counter (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    day         TEXT NOT NULL,                  -- YYYYMMDD
    last_number INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sepa_counter_hub_day        ON sepa_remittances_counter (hub_id, day);
CREATE INDEX        IF NOT EXISTS idx_sepa_remittances_counter_hub ON sepa_remittances_counter (hub_id, is_deleted);
