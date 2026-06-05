-- Lista de lotes del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de LotService.list_lots. Los binds :product_ref y :status deben pasarse ('' = sin filtro).
SELECT id, lot_number, product_ref, manufactured_date, expiry_date,
       quantity_initial, quantity_current, status, notes, created_at
FROM lots_serials_lot
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:product_ref = '' OR product_ref = :product_ref)
  AND (:status      = '' OR status      = :status)
ORDER BY created_at DESC;
