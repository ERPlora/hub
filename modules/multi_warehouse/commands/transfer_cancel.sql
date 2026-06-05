-- Cancelación de un traslado (cualquier estado salvo received/cancelled).
-- Portado de MultiWarehouseService.cancel_transfer. La guarda de estado va en el WHERE:
-- si el traslado ya está received o cancelled, la UPDATE no afecta filas (no-op) y el
-- runtime lo reporta. El :reason se anexa a notes con un marcador [CANCELLED].
-- Runtime inyecta :current_user_id, :now.
UPDATE multi_warehouse_transfer
SET status = 'cancelled',
    notes = TRIM(
        CASE WHEN :reason = '' THEN notes
             ELSE notes || char(10) || '[CANCELLED] ' || :reason END
    ),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :transfer_id
  AND hub_id = :hub_id
  AND is_deleted = 0
  AND status NOT IN ('received', 'cancelled');
