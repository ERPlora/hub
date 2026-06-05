-- Configuración del KDS del hub (singleton). Runtime inyecta :hub_id.
-- Portado de KitchenSettingsService.get_settings (get_kitchen_settings).
-- Si no existe fila aún, la UI usa los valores por defecto del esquema.
SELECT id,
       auto_accept_orders, show_timer, warning_time_minutes, critical_time_minutes,
       items_per_page, auto_refresh_seconds,
       sound_enabled, sound_on_new_order, sound_on_rush,
       auto_bump_enabled, auto_bump_delay_seconds, color_coding_enabled
FROM kitchen_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
