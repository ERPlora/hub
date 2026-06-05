-- Upsert del singleton de ajustes del hub. Portado de SettingsService.update_settings
-- (crea la fila por defecto si falta, luego aplica los campos enviados).
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. La UI/SDK envía SIEMPRE el
-- conjunto completo de campos (rellenando con los actuales/defaults los no tocados).
INSERT INTO services_settings
  (id, hub_id, default_duration, default_buffer_time, default_tax_rate,
   show_prices, show_duration, allow_online_booking, include_tax_in_price, currency,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :default_duration, :default_buffer_time, :default_tax_rate,
   :show_prices, :show_duration, :allow_online_booking, :include_tax_in_price, :currency,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (hub_id) DO UPDATE SET
  default_duration     = :default_duration,
  default_buffer_time  = :default_buffer_time,
  default_tax_rate     = :default_tax_rate,
  show_prices          = :show_prices,
  show_duration        = :show_duration,
  allow_online_booking = :allow_online_booking,
  include_tax_in_price = :include_tax_in_price,
  currency             = :currency,
  updated_by           = :current_user_id,
  updated_at           = :now;
