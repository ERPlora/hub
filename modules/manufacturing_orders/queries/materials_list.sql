-- Líneas de consumo de material de una orden. Runtime inyecta :hub_id.
-- Portado de ManufacturingOrderService.get_mo (rama include_materials).
SELECT id, mo_id, material_ref, quantity_planned, quantity_consumed, unit, status
FROM manufacturing_orders_material
WHERE hub_id = :hub_id AND is_deleted = 0 AND mo_id = :mo_id
ORDER BY created_at ASC;
