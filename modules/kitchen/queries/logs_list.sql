-- Auditoría de acciones del KDS (más recientes primero). Runtime inyecta :hub_id.
-- Portado de KitchenLogService.list_logs. Los filtros opcionales (order_id/action/station_id)
-- se pasan como binds; usar '' para "sin filtro" (NULL-safe vía coalesce).
SELECT id, order_id, order_item_id, station_id, action, performed_by_id, notes, created_at
FROM kitchen_order_log
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:order_id   = '' OR order_id   = :order_id)
  AND (:action     = '' OR action     = :action)
  AND (:station_id = '' OR station_id = :station_id)
ORDER BY created_at DESC
LIMIT 50;
