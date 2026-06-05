-- Detalle completo de un envío por id (scope hub_id). Portado de CarriersService.get_shipment.
-- Los eventos de seguimiento se obtienen aparte vía carriers.shipments.events.
SELECT id, carrier_id, shipment_number, tracking_number, reference,
       origin_address, destination_address, weight_kg, dimensions,
       service_type, status, shipping_cost,
       created_at_local, dispatched_at, delivered_at, notes
FROM carriers_shipment
WHERE id = :shipment_id AND hub_id = :hub_id AND is_deleted = 0;
