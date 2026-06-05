-- Configuración del módulo de comandas del hub. Runtime inyecta :hub_id.
-- Portado de OrdersSettingsService.get_settings (una fila por hub).
SELECT id, auto_print_tickets, show_prep_time, alert_threshold_minutes,
       use_rounds, auto_fire_on_round, default_order_type, sound_on_new_order
FROM kitchen_orders_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
