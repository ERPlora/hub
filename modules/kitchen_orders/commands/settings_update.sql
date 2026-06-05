-- Actualización de la configuración del módulo. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de OrdersSettingsService.update_settings. COALESCE deja sin tocar los no enviados
-- (campos boolean se pasan como 0/1; alert_threshold_minutes como entero).
UPDATE kitchen_orders_settings
SET auto_print_tickets      = COALESCE(:auto_print_tickets, auto_print_tickets),
    show_prep_time          = COALESCE(:show_prep_time, show_prep_time),
    alert_threshold_minutes = COALESCE(:alert_threshold_minutes, alert_threshold_minutes),
    use_rounds              = COALESCE(:use_rounds, use_rounds),
    auto_fire_on_round      = COALESCE(:auto_fire_on_round, auto_fire_on_round),
    default_order_type      = COALESCE(:default_order_type, default_order_type),
    sound_on_new_order      = COALESCE(:sound_on_new_order, sound_on_new_order),
    updated_by              = :current_user_id,
    updated_at              = :now
WHERE hub_id = :hub_id AND is_deleted = 0;
