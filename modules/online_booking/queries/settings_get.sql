-- Configuración (singleton) de la página pública de reservas del hub.
-- Portado de BookingService.get_page_settings / BookingPageSettings.get_settings.
-- NOTA: el "get-or-create" con defaults cuando no existe fila es lógica de runtime
-- (ver WASM-TODO.md); esta query solo devuelve la fila si ya existe.
SELECT id, is_enabled, page_title, welcome_message, primary_color, logo_url,
       require_phone, require_email, allow_staff_selection, allow_notes,
       min_advance_hours, max_advance_days, slot_duration_minutes, buffer_minutes,
       confirmation_message, cancellation_policy
FROM online_booking_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
