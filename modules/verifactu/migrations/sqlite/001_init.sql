-- VeriFactu · esquema inicial (SQLite). Portado de old_modules/m_verifactu/models.py.
-- Cumplimiento de facturación electrónica española (VERI*FACTU), RD 1007/2023:
-- cada factura se transmite a la AEAT con una cadena de hash SHA-256, firma con
-- certificado opcional y generación de QR.
-- Modelos: VerifactuConfig (singleton por hub), VerifactuRecord (registro encadenado),
-- VerifactuEvent (log de auditoría, append-only) y ContingencyQueue (cola de reintentos).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
--
-- NOTA cross-módulo: invoice_id es solo una REFERENCIA almacenada (snapshot de los datos
-- de la factura en el momento del alta). NO hay FK a las tablas privadas del módulo
-- invoice: VeriFactu nunca lee/escribe tablas de invoice; los datos llegan vía el evento
-- público invoice.created / invoice.cancelled.

-- Configuración singleton del módulo VeriFactu por hub.
-- Guarda rutas de certificado, entorno AEAT y parámetros operativos. Una fila por hub_id.
-- certificate_password se guarda cifrado por el runtime (capacidad de host); aquí TEXT.
CREATE TABLE IF NOT EXISTS verifactu_config (
    id                     TEXT PRIMARY KEY,
    hub_id                 TEXT NOT NULL,
    enabled                INTEGER NOT NULL DEFAULT 0,
    mode                   TEXT NOT NULL DEFAULT 'verifactu',   -- verifactu | no_verifactu
    environment            TEXT NOT NULL DEFAULT 'testing',     -- production | testing
    software_name          TEXT NOT NULL DEFAULT 'ERPlora Hub',
    software_version       TEXT NOT NULL DEFAULT '1.0.0',
    software_id            TEXT NOT NULL DEFAULT 'ERPLORA-001',
    software_nif           TEXT NOT NULL DEFAULT '',
    certificate_path       TEXT NOT NULL DEFAULT '',
    certificate_password   TEXT NOT NULL DEFAULT '',            -- cifrado por el runtime
    certificate_expiry     TEXT,                                -- ISO YYYY-MM-DD o NULL
    auto_transmit          INTEGER NOT NULL DEFAULT 1,
    retry_interval_minutes INTEGER NOT NULL DEFAULT 5,
    max_retries            INTEGER NOT NULL DEFAULT 10,
    is_deleted             INTEGER NOT NULL DEFAULT 0,
    deleted_at             TEXT,
    created_by             TEXT,
    updated_by             TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_verifactu_config_hub ON verifactu_config (hub_id);
CREATE INDEX        IF NOT EXISTS idx_verifactu_config_hub ON verifactu_config (hub_id, is_deleted);

-- Registro VeriFactu individual ligado a una factura.
-- Implementa la cadena de hash SHA-256 para integridad y trazabilidad (spec AEAT).
-- Un registro por transmisión de factura (alta) o anulación (anulacion).
-- record_type: alta | anulacion ; invoice_type: F1|F2|F3|R1|R2|R3|R4|R5
-- status: pending | transmitted | accepted | rejected | error | retry
CREATE TABLE IF NOT EXISTS verifactu_record (
    id                      TEXT PRIMARY KEY,
    hub_id                  TEXT NOT NULL,
    record_type             TEXT NOT NULL,
    sequence_number         INTEGER NOT NULL,
    invoice_id              TEXT,                               -- referencia a invoice (sin FK)
    issuer_nif              TEXT NOT NULL,
    issuer_name             TEXT NOT NULL,
    invoice_number          TEXT NOT NULL,
    invoice_date            TEXT NOT NULL,                      -- ISO YYYY-MM-DD
    invoice_type            TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    base_amount             NUMERIC NOT NULL DEFAULT 0,
    tax_rate                NUMERIC NOT NULL DEFAULT 21,
    tax_amount              NUMERIC NOT NULL DEFAULT 0,
    total_amount            NUMERIC NOT NULL DEFAULT 0,
    previous_hash           TEXT NOT NULL DEFAULT '',
    record_hash             TEXT NOT NULL DEFAULT '',
    is_first_record         INTEGER NOT NULL DEFAULT 0,
    generation_timestamp    TEXT NOT NULL,                      -- ISO 8601 con offset
    status                  TEXT NOT NULL DEFAULT 'pending',
    transmission_timestamp  TEXT,
    retry_count             INTEGER NOT NULL DEFAULT 0,
    next_retry_at           TEXT,
    aeat_response_code      TEXT NOT NULL DEFAULT '',
    aeat_response_message   TEXT NOT NULL DEFAULT '',
    aeat_csv                TEXT NOT NULL DEFAULT '',
    qr_url                  TEXT NOT NULL DEFAULT '',
    qr_generated            INTEGER NOT NULL DEFAULT 0,
    xml_content             TEXT NOT NULL DEFAULT '',
    is_deleted              INTEGER NOT NULL DEFAULT 0,
    deleted_at              TEXT,
    created_by              TEXT,
    updated_by              TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT
);
-- Unicidad de la secuencia por (hub, emisor) — clave de la cadena de hash.
CREATE UNIQUE INDEX IF NOT EXISTS uq_verifactu_record_hub_seq      ON verifactu_record (hub_id, issuer_nif, sequence_number);
CREATE UNIQUE INDEX IF NOT EXISTS uq_verifactu_record              ON verifactu_record (hub_id, issuer_nif, invoice_number, invoice_date, record_type);
CREATE INDEX        IF NOT EXISTS ix_verifactu_record_hub_status   ON verifactu_record (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_verifactu_record_hub_nif_num  ON verifactu_record (hub_id, issuer_nif, invoice_number);
CREATE INDEX        IF NOT EXISTS ix_verifactu_record_hub_ts       ON verifactu_record (hub_id, generation_timestamp);
CREATE INDEX        IF NOT EXISTS idx_verifactu_record_hub         ON verifactu_record (hub_id, is_deleted);

-- Log de auditoría de todos los eventos VeriFactu: transmisiones, errores, reintentos,
-- cambios de configuración. Append-only — nunca se actualiza tras crearse.
-- severity: debug | info | warning | error | critical ; details es JSON.
CREATE TABLE IF NOT EXISTS verifactu_event (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    record_id   TEXT,                                          -- ref a verifactu_record (mismo módulo)
    event_type  TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '{}',                    -- JSON
    timestamp   TEXT NOT NULL,                                 -- ISO 8601 con offset
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (record_id) REFERENCES verifactu_record (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_verifactu_event_hub_type     ON verifactu_event (hub_id, event_type);
CREATE INDEX IF NOT EXISTS ix_verifactu_event_hub_severity ON verifactu_event (hub_id, severity);
CREATE INDEX IF NOT EXISTS ix_verifactu_event_hub_ts       ON verifactu_event (hub_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_verifactu_event_hub         ON verifactu_event (hub_id, is_deleted);

-- Cola de registros pendientes de transmisión durante modo contingencia (AEAT caído).
-- Una entrada por registro (relación uno-a-uno vía índice único en record_id).
-- priority: 1=ALTA, 2=NORMAL, 3=BAJA ; status: pending | retrying | failed | cancelled
CREATE TABLE IF NOT EXISTS verifactu_contingencyqueue (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    record_id       TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 2,
    queued_at       TEXT NOT NULL,                             -- ISO 8601 con offset
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    last_error      TEXT NOT NULL DEFAULT '',
    next_attempt_at TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (record_id) REFERENCES verifactu_record (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_verifactu_contingency_record   ON verifactu_contingencyqueue (record_id);
CREATE INDEX        IF NOT EXISTS ix_verifactu_contingency_priority ON verifactu_contingencyqueue (hub_id, priority, queued_at);
CREATE INDEX        IF NOT EXISTS idx_verifactu_contingency_hub     ON verifactu_contingencyqueue (hub_id, is_deleted);
