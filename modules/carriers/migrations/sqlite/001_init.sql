-- Carriers · esquema inicial (SQLite). Portado fielmente de old_modules/m_carriers/models.py.
-- Modelos: Carrier (transportista por tenant), ShippingRate (tarifario por servicio/ruta/peso),
-- Shipment (envío individual con ciclo de vida) y TrackingEvent (eventos de seguimiento).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Columnas JSON portables se almacenan como TEXT (JSON serializado por el runtime/WASM).

-- Transportista configurado para el hub (cuenta por tenant). code es único por hub.
CREATE TABLE IF NOT EXISTS carriers_carrier (
    id                       TEXT PRIMARY KEY,
    hub_id                   TEXT NOT NULL,
    code                     TEXT NOT NULL,
    name                     TEXT NOT NULL,
    provider                 TEXT NOT NULL,             -- seur|mrw|gls|dhl|ups|correos|nacex|zeleris|custom
    service_types            TEXT NOT NULL DEFAULT '[]',-- JSON lista de strings ["express","standard"]
    is_active                INTEGER NOT NULL DEFAULT 1,
    account_credentials_hash TEXT NOT NULL DEFAULT '',  -- hash opaco; los secretos completos viven fuera
    supports_pickup          INTEGER NOT NULL DEFAULT 1,
    supports_tracking        INTEGER NOT NULL DEFAULT 1,
    max_weight_kg            NUMERIC,                   -- NULL = sin límite declarado
    max_dimensions           TEXT,                      -- JSON {"length_cm":..,"width_cm":..,"height_cm":..} o NULL
    is_deleted               INTEGER NOT NULL DEFAULT 0,
    deleted_at               TEXT,
    created_by               TEXT,
    updated_by               TEXT,
    created_at               TEXT NOT NULL,
    updated_at               TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_carrier_hub_code      ON carriers_carrier (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_carrier_hub_provider  ON carriers_carrier (hub_id, provider);
CREATE INDEX        IF NOT EXISTS ix_carrier_hub_active    ON carriers_carrier (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_carriers_carrier_hub ON carriers_carrier (hub_id, is_deleted);

-- Fila de tarifario: precio para un servicio/ruta/bracket de peso de un transportista.
-- valid_from/valid_until acotan la vigencia (NULL = sin acotar por ese extremo).
CREATE TABLE IF NOT EXISTS carriers_shipping_rate (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    carrier_id          TEXT NOT NULL,
    service_type        TEXT NOT NULL,
    origin_country      TEXT NOT NULL,                  -- ISO-2
    destination_country TEXT NOT NULL,                  -- ISO-2
    weight_from_kg      NUMERIC NOT NULL DEFAULT 0,
    weight_to_kg        NUMERIC NOT NULL DEFAULT 0,
    price               NUMERIC NOT NULL DEFAULT 0,
    currency            TEXT NOT NULL DEFAULT 'EUR',
    delivery_days_min   INTEGER NOT NULL DEFAULT 1,
    delivery_days_max   INTEGER NOT NULL DEFAULT 5,
    valid_from          TEXT,                           -- ISO YYYY-MM-DD o NULL
    valid_until         TEXT,                           -- ISO YYYY-MM-DD o NULL
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (carrier_id) REFERENCES carriers_carrier (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_rate_hub_carrier        ON carriers_shipping_rate (hub_id, carrier_id);
CREATE INDEX IF NOT EXISTS ix_rate_hub_route          ON carriers_shipping_rate (hub_id, origin_country, destination_country);
CREATE INDEX IF NOT EXISTS ix_rate_hub_service        ON carriers_shipping_rate (hub_id, service_type);
CREATE INDEX IF NOT EXISTS idx_carriers_shipping_rate_hub ON carriers_shipping_rate (hub_id, is_deleted);

-- Envío individual rastreado a lo largo de su ciclo de vida.
-- shipment_number y tracking_number son únicos por hub. status: created|in_transit|delivered|returned|lost
CREATE TABLE IF NOT EXISTS carriers_shipment (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    carrier_id          TEXT NOT NULL,
    shipment_number     TEXT NOT NULL,                  -- auto SHP-YYYYMMDD-NNNN
    tracking_number     TEXT NOT NULL,                  -- del transportista o placeholder AUTO-<num>
    reference           TEXT NOT NULL DEFAULT '',       -- referencia a documento de negocio (orden, etc.)
    origin_address      TEXT,                           -- JSON {"name":..,"street":..,"city":..,"country":..}
    destination_address TEXT,                           -- JSON
    weight_kg           NUMERIC NOT NULL DEFAULT 0,
    dimensions          TEXT,                           -- JSON o NULL
    service_type        TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'created',
    shipping_cost       NUMERIC NOT NULL DEFAULT 0,
    created_at_local    TEXT,                           -- ISO datetime de creación local
    dispatched_at       TEXT,                           -- ISO datetime al pasar a in_transit
    delivered_at        TEXT,                           -- ISO datetime al pasar a delivered
    notes               TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (carrier_id) REFERENCES carriers_carrier (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_hub_number   ON carriers_shipment (hub_id, shipment_number);
CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_hub_tracking ON carriers_shipment (hub_id, tracking_number);
CREATE INDEX        IF NOT EXISTS ix_shipment_hub_carrier  ON carriers_shipment (hub_id, carrier_id);
CREATE INDEX        IF NOT EXISTS ix_shipment_hub_status   ON carriers_shipment (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_shipment_hub_reference ON carriers_shipment (hub_id, reference);
CREATE INDEX        IF NOT EXISTS idx_carriers_shipment_hub ON carriers_shipment (hub_id, is_deleted);

-- Evento de seguimiento adjunto a un envío. occurred_at marca el orden cronológico.
CREATE TABLE IF NOT EXISTS carriers_tracking_event (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    event_code  TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,                          -- ISO datetime
    raw_data    TEXT,                                   -- JSON crudo del transportista o NULL
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (shipment_id) REFERENCES carriers_shipment (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_tracking_hub_shipment        ON carriers_tracking_event (hub_id, shipment_id);
CREATE INDEX IF NOT EXISTS ix_tracking_hub_occurred        ON carriers_tracking_event (hub_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_carriers_tracking_event_hub ON carriers_tracking_event (hub_id, is_deleted);
