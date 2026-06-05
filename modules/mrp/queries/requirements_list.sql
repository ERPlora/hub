-- Lista de requerimientos de material; filtros opcionales por run y/o producto.
-- Runtime inyecta :hub_id. Portado de MRPService.list_requirements.
-- (:run_id = '' → sin filtro de run; :product_ref = '' → sin filtro de producto.)
SELECT id, run_id, product_ref, required_date,
       quantity_required, quantity_on_hand, quantity_on_order, net_requirement,
       source_type, source_ref
FROM mrp_requirement
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:run_id = ''      OR run_id = :run_id)
  AND (:product_ref = '' OR product_ref = :product_ref)
ORDER BY created_at DESC
LIMIT :limit;
