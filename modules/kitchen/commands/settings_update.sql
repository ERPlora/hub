-- Upsert de la configuración del KDS (singleton por hub). Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now y todos los campos de settings.
-- Portado de KitchenSettingsService.update_settings. El parcheo por-campo (sólo aplicar los
-- valores no nulos) lo resuelve la capa de aplicación / UI enviando el conjunto completo;
-- aquí persistimos el estado entero. ON CONFLICT(hub_id) actualiza la fila existente.
INSERT INTO kitchen_settings
  (id, hub_id, auto_accept_orders, show_timer, warning_time_minutes, critical_time_minutes,
   items_per_page, auto_refresh_seconds, sound_enabled, sound_on_new_order, sound_on_rush,
   auto_bump_enabled, auto_bump_delay_seconds, color_coding_enabled,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :auto_accept_orders, :show_timer, :warning_time_minutes, :critical_time_minutes,
   :items_per_page, :auto_refresh_seconds, :sound_enabled, :sound_on_new_order, :sound_on_rush,
   :auto_bump_enabled, :auto_bump_delay_seconds, :color_coding_enabled,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
  auto_accept_orders      = excluded.auto_accept_orders,
  show_timer              = excluded.show_timer,
  warning_time_minutes    = excluded.warning_time_minutes,
  critical_time_minutes   = excluded.critical_time_minutes,
  items_per_page          = excluded.items_per_page,
  auto_refresh_seconds    = excluded.auto_refresh_seconds,
  sound_enabled           = excluded.sound_enabled,
  sound_on_new_order      = excluded.sound_on_new_order,
  sound_on_rush           = excluded.sound_on_rush,
  auto_bump_enabled       = excluded.auto_bump_enabled,
  auto_bump_delay_seconds = excluded.auto_bump_delay_seconds,
  color_coding_enabled    = excluded.color_coding_enabled,
  updated_by              = :current_user_id,
  updated_at              = :now;
