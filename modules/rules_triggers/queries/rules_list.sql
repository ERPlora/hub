-- Reglas activas del hub ordenadas por priority asc (menor = corre primero).
-- Runtime inyecta :hub_id. Portado de RulesService.list_rules.
-- (:trigger_id = '' => sin filtro por trigger.)
SELECT id, code, name, description, trigger_id, priority,
       conditions, actions, stop_on_match, is_active,
       total_evaluations, total_matches
FROM rules_triggers_rule
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
  AND (:trigger_id = '' OR trigger_id = :trigger_id)
ORDER BY priority ASC;
