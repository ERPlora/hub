-- Avisos e-Transport del hub con filtro opcional por estado. Runtime inyecta :hub_id.
-- Portado de RoFiscalService.list_etransports. :status = '' => sin filtro.
SELECT id, document_number, transport_type, origin_city, destination_city,
       vehicle_plate, departure_date, goods, uit_code, status, submitted_at,
       created_at
FROM fiscal_romania_etransport
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
