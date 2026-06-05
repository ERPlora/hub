-- Cabecera de una pick list por id. Runtime inyecta :hub_id.
-- Portado de PickPackService.get_pick (las líneas se obtienen con picking_packing.picks.lines).
SELECT id, pick_number, order_ref, status, assigned_to_ref,
       started_at, completed_at, notes, created_at
FROM picking_packing_pick_list
WHERE id = :pick_id AND hub_id = :hub_id AND is_deleted = 0;
