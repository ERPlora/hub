-- Courier Integrations · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_courier_integrations/models.py.
-- Modelos: CourierConnection (conexión configurada a la API de un transportista),
-- APICall (registro de auditoría de cada llamada a la API) y ShipmentMapping
-- (mapeo de una referencia de envío local a su nº de seguimiento externo + etiqueta).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Conexión a la API de un transportista concreto (SEUR/MRW/GLS/DHL/UPS/Correos/Nacex).
-- courier_code es único por hub (un solo conector por transportista).
CREATE TABLE IF NOT EXISTS courier_integrations_connection (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    courier_code          TEXT NOT NULL,                 -- seur|mrw|gls|dhl|ups|correos|nacex
    name                  TEXT NOT NULL,
    api_endpoint          TEXT NOT NULL,
    account_number        TEXT NOT NULL DEFAULT '',
    api_credentials_hash  TEXT NOT NULL DEFAULT '',
    environment           TEXT NOT NULL DEFAULT 'test',  -- test|production
    is_active             INTEGER NOT NULL DEFAULT 1,
    last_call_at          TEXT,                          -- ISO 8601 o NULL
    last_call_status      TEXT NOT NULL DEFAULT '',
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_courier_conn_hub_code   ON courier_integrations_connection (hub_id, courier_code);
CREATE INDEX        IF NOT EXISTS ix_courier_conn_hub_active ON courier_integrations_connection (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_courier_connection_hub ON courier_integrations_connection (hub_id, is_deleted);

-- Registro de auditoría de cada llamada a la API de un transportista.
-- call_number es legible (CAPI-YYYYMMDD-NNNN), generado por el runtime/WASM — ver WASM-TODO.
CREATE TABLE IF NOT EXISTS courier_integrations_api_call (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    connection_id     TEXT NOT NULL,
    call_number       TEXT NOT NULL,                     -- CAPI-YYYYMMDD-NNNN
    call_type         TEXT NOT NULL,                     -- create_shipment|get_label|track_shipment|cancel_shipment|get_rate
    request_payload   TEXT,                              -- JSON o NULL
    response_payload  TEXT,                              -- JSON o NULL
    status_code       INTEGER,
    status            TEXT NOT NULL DEFAULT 'success',   -- success|failed|timeout
    called_at         TEXT NOT NULL,
    response_time_ms  INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (connection_id) REFERENCES courier_integrations_connection (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_courier_call_hub_conn_type ON courier_integrations_api_call (hub_id, connection_id, call_type);
CREATE INDEX IF NOT EXISTS ix_courier_call_hub_status    ON courier_integrations_api_call (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_courier_call_called_at     ON courier_integrations_api_call (called_at);
CREATE INDEX IF NOT EXISTS idx_courier_api_call_hub      ON courier_integrations_api_call (hub_id, is_deleted);

-- Mapeo de una referencia de envío local a su nº de seguimiento del transportista + etiqueta.
CREATE TABLE IF NOT EXISTS courier_integrations_shipment_mapping (
    id                        TEXT PRIMARY KEY,
    hub_id                    TEXT NOT NULL,
    connection_id             TEXT NOT NULL,
    local_shipment_ref        TEXT NOT NULL,
    external_tracking_number  TEXT NOT NULL DEFAULT '',
    label_url                 TEXT NOT NULL DEFAULT '',
    status_at_courier         TEXT NOT NULL DEFAULT '',
    last_synced_at            TEXT,
    is_deleted                INTEGER NOT NULL DEFAULT 0,
    deleted_at                TEXT,
    created_by                TEXT,
    updated_by                TEXT,
    created_at                TEXT NOT NULL,
    updated_at                TEXT,
    FOREIGN KEY (connection_id) REFERENCES courier_integrations_connection (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_courier_map_hub_local_ref   ON courier_integrations_shipment_mapping (hub_id, local_shipment_ref);
CREATE INDEX IF NOT EXISTS ix_courier_map_hub_tracking    ON courier_integrations_shipment_mapping (hub_id, external_tracking_number);
CREATE INDEX IF NOT EXISTS idx_courier_shipment_mapping_hub ON courier_integrations_shipment_mapping (hub_id, is_deleted);
