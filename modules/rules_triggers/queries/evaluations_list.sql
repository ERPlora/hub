-- Evaluaciones recientes del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de RulesService.list_evaluations (orden por evaluated_at desc).
-- (:rule_id = '' => todas las reglas. :matched = -1 => sin filtro; 0/1 => filtra por matched.)
SELECT id, rule_id, trigger_id, evaluated_at, matched,
       input_data, output, execution_time_ms, error_message
FROM rules_triggers_evaluation
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:rule_id = '' OR rule_id = :rule_id)
  AND (:matched = -1 OR matched = :matched)
ORDER BY evaluated_at DESC;
