-- Listado de pick lists con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de PickPackService.list_picks. Binds :status y :assigned_to ('' = sin filtro).
SELECT id, pick_number, order_ref, status, assigned_to_ref,
       started_at, completed_at, notes, created_at
FROM picking_packing_pick_list
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status      = '' OR status          = :status)
  AND (:assigned_to = '' OR assigned_to_ref = :assigned_to)
ORDER BY created_at DESC
LIMIT :limit;
