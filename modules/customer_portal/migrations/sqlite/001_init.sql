-- Customer Portal · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_customer_portal/models.py.
-- Modelos: CustomerAccount (cuenta self-service del cliente final),
-- PortalSession (sesión autenticada de una cuenta) y PortalInvitation
-- (invitación pendiente para crear una cuenta).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Cuenta de portal self-service para un cliente final del hub.
-- customer_email es único por hub (índice ix_customer_portal_account_hub_email).
-- password_hash guarda 'salt$hash' (sha256) — el hashing/verificación va a WASM.
CREATE TABLE IF NOT EXISTS customer_portal_account (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    customer_email  TEXT NOT NULL,
    customer_tax_id TEXT NOT NULL DEFAULT '',
    password_hash   TEXT NOT NULL DEFAULT '',
    email_verified  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'invited',  -- invited|active|suspended|closed
    invited_at      TEXT,                             -- ISO datetime o NULL
    activated_at    TEXT,                             -- ISO datetime o NULL
    last_login_at   TEXT,                             -- ISO datetime o NULL
    language        TEXT NOT NULL DEFAULT 'en',
    notes           TEXT NOT NULL DEFAULT '',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_portal_account_hub_email  ON customer_portal_account (hub_id, customer_email);
CREATE INDEX        IF NOT EXISTS ix_customer_portal_account_hub_status ON customer_portal_account (hub_id, status);
CREATE INDEX        IF NOT EXISTS idx_customer_portal_account_hub       ON customer_portal_account (hub_id, is_deleted);

-- Sesión autenticada de una CustomerAccount (token de 24h).
-- session_token es único; expires_at marca el fin de validez; is_active permite revocar.
CREATE TABLE IF NOT EXISTS customer_portal_session (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    account_id    TEXT NOT NULL,
    session_token TEXT NOT NULL,
    expires_at    TEXT NOT NULL,                  -- ISO datetime
    is_active     INTEGER NOT NULL DEFAULT 1,
    ip_address    TEXT NOT NULL DEFAULT '',
    user_agent    TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (account_id) REFERENCES customer_portal_account (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_portal_session_token       ON customer_portal_session (session_token);
CREATE INDEX        IF NOT EXISTS ix_customer_portal_session_hub_account ON customer_portal_session (hub_id, account_id);
CREATE INDEX        IF NOT EXISTS ix_customer_portal_session_hub_active  ON customer_portal_session (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_customer_portal_session_hub        ON customer_portal_session (hub_id, is_deleted);

-- Invitación pendiente para crear una CustomerAccount (token de 7 días).
-- invitation_token es único; used_at != NULL marca la invitación ya redimida.
-- invited_by_ref es referencia libre al emisor (no acopla con esquemas de auth).
CREATE TABLE IF NOT EXISTS customer_portal_invitation (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    customer_email   TEXT NOT NULL,
    customer_name    TEXT NOT NULL DEFAULT '',
    invitation_token TEXT NOT NULL,
    invited_by_ref   TEXT NOT NULL DEFAULT '',
    expires_at       TEXT NOT NULL,               -- ISO datetime
    used_at          TEXT,                         -- ISO datetime o NULL
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_portal_invitation_token     ON customer_portal_invitation (invitation_token);
CREATE INDEX        IF NOT EXISTS ix_customer_portal_invitation_hub_email ON customer_portal_invitation (hub_id, customer_email);
CREATE INDEX        IF NOT EXISTS idx_customer_portal_invitation_hub      ON customer_portal_invitation (hub_id, is_deleted);
