-- Aprobar una sugerencia de aprovisionamiento pendiente. Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado de MRPService.approve_suggestion.
-- La guarda de estado (solo 'pending' puede aprobarse) la añade el WHERE: si la fila
-- no está pending, no se actualiza ninguna fila (el runtime trata 0 filas como error de
-- estado). approved_by_ref guarda el actor; las notas se anexan en runtime (ver WASM-TODO).
UPDATE mrp_suggestion
SET status = 'approved',
    approved_by_ref = :current_user_id,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :suggestion_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
