-- Cerrar una oportunidad como 'lost' con motivo obligatorio. Portado de OpportunityService.mark_lost.
-- Guarda: solo si está abierta (stage NOT IN ('won','lost')) → no se puede perder una ganada ni
-- re-perder una perdida. La obligatoriedad de :reason la garantiza el schema (minLength 1).
UPDATE opportunities_opportunity
SET stage        = 'lost',
    probability  = 0,
    close_reason = :reason,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :opportunity_id AND hub_id = :hub_id AND is_deleted = 0
  AND stage NOT IN ('won', 'lost');
