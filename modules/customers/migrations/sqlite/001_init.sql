-- Customers · esquema inicial (SQLite). Portado fielmente de old_modules/m_customers/models.py (v2.2.10).
-- Modelos: CustomerGroup, CustomerTag, CustomerField, CustomerFieldValue, Customer,
-- CustomerActivity (timeline), CustomerNote + M2M groups/tags.
-- Contrato de fila estándar hub-next (§2.5): hub_id + soft-delete + auditoría.

CREATE TABLE IF NOT EXISTS customers_customergroup (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    discount_percent NUMERIC NOT NULL DEFAULT 0,
    color            TEXT NOT NULL DEFAULT 'primary',
    is_active        INTEGER NOT NULL DEFAULT 1,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_custgroup_hub ON customers_customergroup (hub_id, is_active);

CREATE TABLE IF NOT EXISTS customers_customertag (
    id         TEXT PRIMARY KEY,
    hub_id     TEXT NOT NULL,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT 'primary',
    is_active  INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_custtag_hub ON customers_customertag (hub_id, is_active);

CREATE TABLE IF NOT EXISTS customers_customerfield (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    field_type  TEXT NOT NULL DEFAULT 'text',   -- text|number|date|boolean|select|textarea
    options     TEXT NOT NULL DEFAULT '[]',
    is_required INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_custfield_hub ON customers_customerfield (hub_id, is_active);

CREATE TABLE IF NOT EXISTS customers_customer (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    name               TEXT NOT NULL,
    email              TEXT NOT NULL DEFAULT '',
    phone              TEXT NOT NULL DEFAULT '',
    tax_id             TEXT NOT NULL DEFAULT '',
    address            TEXT NOT NULL DEFAULT '',
    city               TEXT NOT NULL DEFAULT '',
    postal_code        TEXT NOT NULL DEFAULT '',
    country            TEXT NOT NULL DEFAULT '',
    avatar             TEXT NOT NULL DEFAULT '',
    notes              TEXT NOT NULL DEFAULT '',
    is_active          INTEGER NOT NULL DEFAULT 1,
    lifecycle_stage    TEXT NOT NULL DEFAULT 'lead',   -- lead|prospect|first_purchase|active|at_risk|dormant|churned|vip
    source             TEXT NOT NULL DEFAULT 'walk_in',
    company_name       TEXT NOT NULL DEFAULT '',
    birthday           TEXT,
    anniversary        TEXT,
    preferred_channel  TEXT NOT NULL DEFAULT 'none',   -- email|sms|whatsapp|phone|none
    marketing_consent  INTEGER NOT NULL DEFAULT 0,
    consent_date       TEXT,
    total_purchases    INTEGER NOT NULL DEFAULT 0,
    total_spent        NUMERIC NOT NULL DEFAULT 0,
    last_purchase_date TEXT,
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_customers_hub_email     ON customers_customer (hub_id, email);
CREATE INDEX IF NOT EXISTS ix_customers_hub_phone     ON customers_customer (hub_id, phone);
CREATE INDEX IF NOT EXISTS ix_customers_hub_tax_id    ON customers_customer (hub_id, tax_id);
CREATE INDEX IF NOT EXISTS ix_customers_hub_active    ON customers_customer (hub_id, is_active);
CREATE INDEX IF NOT EXISTS ix_customers_hub_lifecycle ON customers_customer (hub_id, lifecycle_stage);

CREATE TABLE IF NOT EXISTS customers_customerfieldvalue (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    field_id    TEXT NOT NULL,
    value       TEXT NOT NULL DEFAULT '',
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers_customer (id) ON DELETE CASCADE,
    FOREIGN KEY (field_id)    REFERENCES customers_customerfield (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_field_value ON customers_customerfieldvalue (customer_id, field_id);

CREATE TABLE IF NOT EXISTS customers_customeractivity (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    customer_id         TEXT NOT NULL,
    activity_type       TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    extra_metadata      TEXT NOT NULL DEFAULT '{}',
    related_object_id   TEXT,
    related_object_type TEXT NOT NULL DEFAULT '',
    performed_by        TEXT,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers_customer (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_activity_hub_customer_created ON customers_customeractivity (hub_id, customer_id, created_at);
CREATE INDEX IF NOT EXISTS ix_activity_hub_type            ON customers_customeractivity (hub_id, activity_type);

CREATE TABLE IF NOT EXISTS customers_customernote (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    content     TEXT NOT NULL,
    author_id   TEXT,
    author_name TEXT NOT NULL DEFAULT '',
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT, created_by TEXT, updated_by TEXT, created_at TEXT, updated_at TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers_customer (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_custnote_customer ON customers_customernote (hub_id, customer_id);

-- M2M customer ↔ group / tag.
CREATE TABLE IF NOT EXISTS customers_customer_groups (
    customer_id TEXT NOT NULL,
    group_id    TEXT NOT NULL,
    PRIMARY KEY (customer_id, group_id),
    FOREIGN KEY (customer_id) REFERENCES customers_customer (id) ON DELETE CASCADE,
    FOREIGN KEY (group_id)    REFERENCES customers_customergroup (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customers_customer_tags (
    customer_id TEXT NOT NULL,
    tag_id      TEXT NOT NULL,
    PRIMARY KEY (customer_id, tag_id),
    FOREIGN KEY (customer_id) REFERENCES customers_customer (id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)      REFERENCES customers_customertag (id) ON DELETE CASCADE
);
