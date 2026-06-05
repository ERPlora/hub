-- Envíos del hub (más recientes primero) con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de CarriersService.list_shipments. Binds: :carrier_id, :status ('' = sin filtro),
-- :limit (máximo de filas). El conteo total lo deriva el SDK del listado.
SELECT id, carrier_id, shipment_number, tracking_number, reference,
       weight_kg, service_type, status, shipping_cost,
       created_at_local, dispatched_at, delivered_at
FROM carriers_shipment
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:carrier_id = '' OR carrier_id = :carrier_id)
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
