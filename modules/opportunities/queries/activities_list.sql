-- Registro de actividades de una oportunidad (scope hub_id).
-- Portado del bloque include_activities de OpportunityService.get_opportunity.
SELECT id, opportunity_id, activity_type, description, scheduled_for,
       completed_at, completed_by_ref, created_at
FROM opportunities_activity
WHERE opportunity_id = :opportunity_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC;
