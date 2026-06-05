-- Desactivación lógica de una regla (NO borra: la saca de futuras evaluaciones).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de RulesService.deactivate_rule.
UPDATE rules_triggers_rule
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :rule_id AND hub_id = :hub_id AND is_deleted = 0;
