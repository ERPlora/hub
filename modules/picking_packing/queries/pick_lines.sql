-- Líneas de una pick list. Runtime inyecta :hub_id.
-- Portado de PickPackService.get_pick (sección de líneas).
SELECT id, pick_list_id, product_ref, quantity_requested, quantity_picked,
       location_ref, lot_ref, is_complete
FROM picking_packing_pick_line
WHERE pick_list_id = :pick_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
