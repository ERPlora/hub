-- Rechazar una sugerencia de aprovisionamiento pendiente (motivo requerido por schema).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de MRPService.reject_suggestion.
-- Solo 'pending' puede rechazarse (guarda en el WHERE). El append del rastro
-- "[REJECTED] <reason>" a notes se compone en runtime (capacidad de reloj) — ver WASM-TODO.
UPDATE mrp_suggestion
SET status = 'rejected',
    approved_by_ref = :current_user_id,
    notes = :reason,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :suggestion_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
