-- Online Booking · esquema inicial (SQLite). Portado fielmente de
-- old_modules/m_online_booking/models.py.
-- Modelos: BookingPageSettings (singleton por hub: configuración de la página pública
-- de reservas) y OnlineBooking (una reserva concreta, manual o desde la página pública).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Configuración de la página pública de reservas. Singleton por hub: garantizado por
-- el índice único ix_ob_settings_hub. El "get-or-create" del singleton (defaults) y la
-- validación de reglas (min_advance_hours / max_advance_days / slot_duration) son lógica
-- de runtime — ver WASM-TODO.md.
CREATE TABLE IF NOT EXISTS online_booking_settings (
    id                    TEXT PRIMARY KEY,
    hub_id                TEXT NOT NULL,
    is_enabled            INTEGER NOT NULL DEFAULT 0,
    page_title            TEXT NOT NULL DEFAULT 'Book an Appointment',
    welcome_message       TEXT NOT NULL DEFAULT '',
    primary_color         TEXT NOT NULL DEFAULT '#6366f1',
    logo_url              TEXT NOT NULL DEFAULT '',
    require_phone         INTEGER NOT NULL DEFAULT 1,
    require_email         INTEGER NOT NULL DEFAULT 1,
    allow_staff_selection INTEGER NOT NULL DEFAULT 1,
    allow_notes           INTEGER NOT NULL DEFAULT 1,
    min_advance_hours     INTEGER NOT NULL DEFAULT 2,
    max_advance_days      INTEGER NOT NULL DEFAULT 30,
    slot_duration_minutes INTEGER NOT NULL DEFAULT 30,
    buffer_minutes        INTEGER NOT NULL DEFAULT 0,
    confirmation_message  TEXT NOT NULL DEFAULT 'Your appointment has been booked successfully. We will confirm it shortly.',
    cancellation_policy   TEXT NOT NULL DEFAULT '',
    is_deleted            INTEGER NOT NULL DEFAULT 0,
    deleted_at            TEXT,
    created_by            TEXT,
    updated_by            TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ob_settings_hub        ON online_booking_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_online_booking_settings_hub ON online_booking_settings (hub_id, is_deleted);

-- Reserva online. customer_id/service_id/staff_id se guardan como TEXT (UUID) + el nombre
-- denormalizado para resiliencia cross-módulo (sin FK a customers — referencia por contrato).
-- booking_reference (BK-00001) lo genera el runtime con contador atómico por hub.
-- Las transiciones de estado (confirm/cancel/complete/no_show), la detección de doble
-- reserva por staff y el convert_to_target (Appointment/Reservation) son lógica de
-- runtime — ver WASM-TODO.md.
CREATE TABLE IF NOT EXISTS online_booking_booking (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    booking_reference   TEXT NOT NULL DEFAULT '',
    customer_id         TEXT,
    customer_name       TEXT NOT NULL,
    customer_email      TEXT NOT NULL DEFAULT '',
    customer_phone      TEXT NOT NULL DEFAULT '',
    service_id          TEXT,
    service_name        TEXT NOT NULL,
    staff_id            TEXT,
    staff_name          TEXT NOT NULL DEFAULT '',
    booking_date        TEXT NOT NULL,                       -- ISO YYYY-MM-DD
    booking_time        TEXT NOT NULL,                       -- ISO HH:MM:SS
    duration_minutes    INTEGER NOT NULL DEFAULT 30,
    status              TEXT NOT NULL DEFAULT 'pending',     -- pending|confirmed|cancelled|completed|no_show
    booking_type        TEXT NOT NULL DEFAULT 'appointment', -- appointment|table_reservation
    target_type         TEXT,                                -- appointment|table_reservation (tras convert)
    target_id           TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    confirmed_at        TEXT,
    cancelled_at        TEXT,
    cancellation_reason TEXT NOT NULL DEFAULT '',
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS ix_ob_hub_status        ON online_booking_booking (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_ob_hub_date          ON online_booking_booking (hub_id, booking_date);
CREATE INDEX IF NOT EXISTS ix_ob_hub_reference     ON online_booking_booking (hub_id, booking_reference);
CREATE INDEX IF NOT EXISTS ix_ob_hub_email         ON online_booking_booking (hub_id, customer_email);
CREATE INDEX IF NOT EXISTS ix_ob_hub_target        ON online_booking_booking (hub_id, target_id);
CREATE INDEX IF NOT EXISTS idx_online_booking_booking_hub ON online_booking_booking (hub_id, is_deleted);
