-- Transición draft → in_progress. Runtime inyecta :current_user_id, :now, :hub_id.
-- Portado de PickPackService.start_pick. La guarda de estado se expresa en el WHERE
-- (status='draft'): si la fila no está en draft no se actualiza ninguna fila.
UPDATE picking_packing_pick_list
SET status = 'in_progress',
    started_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :pick_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
