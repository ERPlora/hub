-- Lista de números de serie del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de LotService.list_serials. Los binds :product_ref y :status deben pasarse ('' = sin filtro).
SELECT id, serial, product_ref, lot_id, status, current_location_ref,
       sold_at, sold_to_customer, notes, created_at
FROM lots_serials_serial
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:product_ref = '' OR product_ref = :product_ref)
  AND (:status      = '' OR status      = :status)
ORDER BY created_at DESC;
