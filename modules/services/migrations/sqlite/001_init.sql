-- Services · esquema inicial (SQLite). Portado fielmente de old_modules/m_services/models.py.
-- Modelos: ServicesSettings (singleton), ServiceCategory (jerárquica), Service,
-- ServiceVariant, ServiceAddon (+ M2M addon↔service), ServicePackage, ServicePackageItem.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración singleton por hub.
CREATE TABLE IF NOT EXISTS services_settings (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    default_duration     INTEGER NOT NULL DEFAULT 60,
    default_buffer_time  INTEGER NOT NULL DEFAULT 0,
    default_tax_rate     NUMERIC NOT NULL DEFAULT 21.00,
    show_prices          INTEGER NOT NULL DEFAULT 1,
    show_duration        INTEGER NOT NULL DEFAULT 1,
    allow_online_booking INTEGER NOT NULL DEFAULT 1,
    include_tax_in_price INTEGER NOT NULL DEFAULT 1,
    currency             TEXT NOT NULL DEFAULT 'EUR',
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT,
    updated_at           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_services_settings_hub ON services_settings (hub_id);

-- Categoría de servicios (jerárquica vía parent_id).
CREATE TABLE IF NOT EXISTS services_category (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id   TEXT,
    icon        TEXT NOT NULL DEFAULT '',
    color       TEXT NOT NULL DEFAULT '',
    image       TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    FOREIGN KEY (parent_id) REFERENCES services_category (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_services_category_hub_slug ON services_category (hub_id, slug);
CREATE INDEX        IF NOT EXISTS ix_services_category_order     ON services_category (hub_id, sort_order);
CREATE INDEX        IF NOT EXISTS ix_services_category_active    ON services_category (hub_id, is_active);

-- Servicio (precio, duración, opciones de reserva).
CREATE TABLE IF NOT EXISTS services_service (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    name                  TEXT NOT NULL,
    slug                  TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    short_description     TEXT NOT NULL DEFAULT '',
    category_id           TEXT,
    pricing_type          TEXT NOT NULL DEFAULT 'fixed',   -- fixed|hourly|from|variable|free
    price                 NUMERIC NOT NULL DEFAULT 0.00,
    min_price             NUMERIC,
    max_price             NUMERIC,
    cost                  NUMERIC NOT NULL DEFAULT 0.00,
    tax_rate              NUMERIC,
    duration_minutes      INTEGER NOT NULL DEFAULT 60,
    buffer_before         INTEGER NOT NULL DEFAULT 0,
    buffer_after          INTEGER NOT NULL DEFAULT 0,
    max_capacity          INTEGER NOT NULL DEFAULT 1,
    image                 TEXT NOT NULL DEFAULT '',
    icon                  TEXT NOT NULL DEFAULT '',
    color                 TEXT NOT NULL DEFAULT '',
    is_bookable           INTEGER NOT NULL DEFAULT 1,
    requires_confirmation INTEGER NOT NULL DEFAULT 0,
    allow_online_booking  INTEGER NOT NULL DEFAULT 1,
    sort_order            INTEGER NOT NULL DEFAULT 0,
    is_active             INTEGER NOT NULL DEFAULT 1,
    is_featured           INTEGER NOT NULL DEFAULT 0,
    sku                   TEXT NOT NULL DEFAULT '',
    barcode               TEXT NOT NULL DEFAULT '',
    notes                 TEXT NOT NULL DEFAULT '',
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT,
    updated_at            TEXT,
    FOREIGN KEY (category_id) REFERENCES services_category (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_services_service_hub_slug      ON services_service (hub_id, slug);
CREATE INDEX        IF NOT EXISTS ix_services_service_active_book   ON services_service (hub_id, is_active, is_bookable);
CREATE INDEX        IF NOT EXISTS ix_services_service_category      ON services_service (hub_id, category_id);
CREATE INDEX        IF NOT EXISTS ix_services_service_name          ON services_service (hub_id, name);

-- Variante de un servicio (ajustes de precio/duración).
CREATE TABLE IF NOT EXISTS services_variant (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    service_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    price_adjustment    NUMERIC NOT NULL DEFAULT 0.00,
    duration_adjustment INTEGER NOT NULL DEFAULT 0,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    is_active           INTEGER NOT NULL DEFAULT 1,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT,
    updated_at          TEXT,
    FOREIGN KEY (service_id) REFERENCES services_service (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_services_variant_service_name ON services_variant (service_id, name);
CREATE INDEX        IF NOT EXISTS ix_services_variant_service      ON services_variant (hub_id, service_id, is_active);

-- Complemento (addon) que se asocia a servicios (M2M).
CREATE TABLE IF NOT EXISTS services_addon (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    price            NUMERIC NOT NULL DEFAULT 0.00,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    is_active        INTEGER NOT NULL DEFAULT 1,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_services_addon_hub ON services_addon (hub_id, is_deleted);

-- M2M addon ↔ servicio.
CREATE TABLE IF NOT EXISTS services_addon_services (
    addon_id   TEXT NOT NULL,
    service_id TEXT NOT NULL,
    PRIMARY KEY (addon_id, service_id),
    FOREIGN KEY (addon_id)   REFERENCES services_addon (id)   ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services_service (id) ON DELETE CASCADE
);

-- Paquete: combina varios servicios con descuento.
CREATE TABLE IF NOT EXISTS services_package (
    id             TEXT PRIMARY KEY,
    hub_id         TEXT NOT NULL,
    name           TEXT NOT NULL,
    slug           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    discount_type  TEXT NOT NULL DEFAULT 'percentage',   -- percentage|fixed
    discount_value NUMERIC NOT NULL DEFAULT 0.00,
    fixed_price    NUMERIC,
    validity_days  INTEGER,
    max_uses       INTEGER,
    image          TEXT NOT NULL DEFAULT '',
    sort_order     INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 1,
    is_featured    INTEGER NOT NULL DEFAULT 0,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT,
    created_by     TEXT,
    updated_by     TEXT,
    created_at     TEXT,
    updated_at     TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_services_package_hub_slug ON services_package (hub_id, slug);
CREATE INDEX        IF NOT EXISTS ix_services_package_active    ON services_package (hub_id, is_active);

-- Línea de paquete (modelo through paquete ↔ servicio).
CREATE TABLE IF NOT EXISTS services_packageitem (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    package_id  TEXT NOT NULL,
    service_id  TEXT NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    FOREIGN KEY (package_id) REFERENCES services_package (id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services_service (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_services_packageitem_pkg_svc ON services_packageitem (package_id, service_id);
CREATE INDEX        IF NOT EXISTS ix_services_packageitem_package  ON services_packageitem (hub_id, package_id, is_deleted);
