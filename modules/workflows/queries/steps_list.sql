-- Pasos de una ejecución, ordenados. Runtime inyecta :hub_id.
-- Portado de WorkflowService.get_run (include_steps): pasos por run_id.
SELECT id, run_id, step_order, step_type, params, result, status,
       started_at, completed_at
FROM workflows_step
WHERE run_id = :run_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY step_order ASC;
