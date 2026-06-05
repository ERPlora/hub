-- Una regla por id (scope hub_id). Portado de RulesService.get_rule.
SELECT id, code, name, description, trigger_id, priority,
       conditions, actions, stop_on_match, is_active,
       total_evaluations, total_matches
FROM rules_triggers_rule
WHERE id = :rule_id AND hub_id = :hub_id AND is_deleted = 0;
