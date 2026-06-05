-- Envío localizado por su tracking_number (scope hub_id). Portado de CarriersService.track_shipment.
-- Devuelve la cabecera; los eventos se obtienen con carriers.shipments.events sobre el id resultante.
SELECT id, carrier_id, shipment_number, tracking_number, reference,
       weight_kg, service_type, status, shipping_cost,
       created_at_local, dispatched_at, delivered_at
FROM carriers_shipment
WHERE tracking_number = :tracking_number AND hub_id = :hub_id AND is_deleted = 0;
