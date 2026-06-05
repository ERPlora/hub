-- Leads · esquema inicial (SQLite). Portado fielmente de old_modules/m_leads/models.py.
-- Modelos: LeadSource (canal/origen de adquisición) y Lead (prospecto CRM con ciclo de
-- vida new → contacted → qualified/unqualified → converted/lost).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Origen del lead: canal por el que se adquirió (web, referido, etc.).
-- code es único por hub y es el identificador estable referenciado por los leads.
CREATE TABLE IF NOT EXISTS leads_source (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_source_hub_code   ON leads_source (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_leads_source_hub_active ON leads_source (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_leads_source_hub       ON leads_source (hub_id, is_deleted);

-- Lead (prospecto): contacto que aún no es cliente. lead_number autogenerado
-- LD-YYYYMMDD-NNNN (secuencia por hub+día — el contador atómico va a WASM/runtime).
-- status: new|contacted|qualified|unqualified|converted|lost.
-- assigned_to_ref: referencia laxa a usuario (sin FK a tablas de otro módulo).
CREATE TABLE IF NOT EXISTS leads_lead (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    lead_number      TEXT NOT NULL,
    first_name       TEXT NOT NULL,
    last_name        TEXT NOT NULL DEFAULT '',
    email            TEXT NOT NULL DEFAULT '',
    phone            TEXT NOT NULL DEFAULT '',
    company          TEXT NOT NULL DEFAULT '',
    job_title        TEXT NOT NULL DEFAULT '',
    source_id        TEXT,
    status           TEXT NOT NULL DEFAULT 'new',
    assigned_to_ref  TEXT NOT NULL DEFAULT '',
    estimated_value  NUMERIC NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    contacted_at     TEXT,                          -- ISO timestamp o NULL
    qualified_at     TEXT,                          -- ISO timestamp o NULL
    converted_at     TEXT,                          -- ISO timestamp o NULL
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (source_id) REFERENCES leads_source (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_leads_hub_status   ON leads_lead (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_leads_hub_assigned ON leads_lead (hub_id, assigned_to_ref);
CREATE INDEX IF NOT EXISTS ix_leads_hub_number   ON leads_lead (hub_id, lead_number);
CREATE INDEX IF NOT EXISTS idx_leads_lead_hub    ON leads_lead (hub_id, is_deleted);
