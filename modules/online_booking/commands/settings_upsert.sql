-- Crear o actualizar la configuración (singleton por hub) de la página de reservas.
-- Portado de BookingService (get_page_settings) + BookingPageSettingsUpdate schema.
-- UPSERT sobre el índice único ix_ob_settings_hub(hub_id): si no existe la crea con
-- :new_id, si existe actualiza los campos editables. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now.
INSERT INTO online_booking_settings
  (id, hub_id, is_enabled, page_title, welcome_message, primary_color, logo_url,
   require_phone, require_email, allow_staff_selection, allow_notes,
   min_advance_hours, max_advance_days, slot_duration_minutes, buffer_minutes,
   confirmation_message, cancellation_policy,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :is_enabled, :page_title, :welcome_message, :primary_color, :logo_url,
   :require_phone, :require_email, :allow_staff_selection, :allow_notes,
   :min_advance_hours, :max_advance_days, :slot_duration_minutes, :buffer_minutes,
   :confirmation_message, :cancellation_policy,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
  is_enabled            = :is_enabled,
  page_title            = :page_title,
  welcome_message       = :welcome_message,
  primary_color         = :primary_color,
  logo_url              = :logo_url,
  require_phone         = :require_phone,
  require_email         = :require_email,
  allow_staff_selection = :allow_staff_selection,
  allow_notes           = :allow_notes,
  min_advance_hours     = :min_advance_hours,
  max_advance_days      = :max_advance_days,
  slot_duration_minutes = :slot_duration_minutes,
  buffer_minutes        = :buffer_minutes,
  confirmation_message  = :confirmation_message,
  cancellation_policy   = :cancellation_policy,
  is_deleted            = 0,
  deleted_at            = NULL,
  updated_by            = :current_user_id,
  updated_at            = :now;
