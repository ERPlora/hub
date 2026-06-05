-- Lista de BOMs del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de BOMService.list_boms. Los binds :product_ref y :status deben pasarse
-- ('' = sin filtro). Orden por created_at descendente (las más recientes primero).
SELECT id, code, name, product_ref, version, status, is_default,
       effective_from, effective_to, notes, approved_by_ref, approved_at, created_at
FROM bom_bom
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:product_ref = '' OR product_ref = :product_ref)
  AND (:status      = '' OR status      = :status)
ORDER BY created_at DESC;
