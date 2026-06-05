-- Líneas (componentes) de una BOM. Runtime inyecta :hub_id.
-- Portado de BOMService.get_bom (include_components) y del serializer de routes.py.
SELECT id, bom_id, component_ref, quantity, unit, scrap_pct, is_optional, sub_bom_id
FROM bom_component
WHERE hub_id = :hub_id AND bom_id = :bom_id AND is_deleted = 0
ORDER BY component_ref ASC;
