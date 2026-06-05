-- Marcar una actividad programada como completada (completed_at = ahora).
-- Portado de OpportunityService.complete_activity. Guarda: solo si aún no estaba completada.
UPDATE opportunities_activity
SET completed_at     = :now,
    completed_by_ref = :current_user_id,
    updated_by       = :current_user_id,
    updated_at       = :now
WHERE id = :activity_id AND hub_id = :hub_id AND is_deleted = 0
  AND completed_at IS NULL;
