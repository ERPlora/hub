-- Una BOM por id (scope hub_id). Portado de BOMService.get_bom (cabecera).
-- Las líneas de componentes se obtienen con la query bom.components.list.
SELECT id, code, name, product_ref, version, status, is_default,
       effective_from, effective_to, notes, approved_by_ref, approved_at, created_at
FROM bom_bom
WHERE id = :bom_id AND hub_id = :hub_id AND is_deleted = 0;
