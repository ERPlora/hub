-- Mapeos de envío local → seguimiento externo del hub. Runtime inyecta :hub_id.
-- Derivado del modelo ShipmentMapping (no había query directa en legacy, pero se necesita
-- para resolver shipment_mapping_id en operaciones de etiqueta/seguimiento/cancelación).
-- (:connection_id = '' → sin filtro; :local_shipment_ref = '' → sin filtro.)
SELECT id, connection_id, local_shipment_ref, external_tracking_number,
       label_url, status_at_courier, last_synced_at
FROM courier_integrations_shipment_mapping
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:local_shipment_ref = '' OR local_shipment_ref = :local_shipment_ref)
ORDER BY last_synced_at DESC, created_at DESC;
