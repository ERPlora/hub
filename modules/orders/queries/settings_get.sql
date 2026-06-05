-- Configuración singleton del módulo orders para el hub. Portado de OrderService.get_settings.
-- Si no hay fila, la UI/SDK aplica los defaults (auto_confirm=0, default_channel='phone', etc.).
SELECT id, auto_confirm, require_customer, default_channel,
       notify_on_new_order, allow_partial_fulfillment
FROM orders_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
