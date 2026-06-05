-- Eventos de seguimiento de un envío, en orden cronológico. Runtime inyecta :hub_id.
-- Portado de la rama include_events de CarriersService.get_shipment.
SELECT id, shipment_id, event_code, description, location, occurred_at, raw_data
FROM carriers_tracking_event
WHERE shipment_id = :shipment_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY occurred_at ASC;
