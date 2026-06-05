-- Desactivación lógica de un trigger (NO borra: lo saca de futuras evaluaciones).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de RulesService.deactivate_trigger.
UPDATE rules_triggers_trigger
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :trigger_id AND hub_id = :hub_id AND is_deleted = 0;
