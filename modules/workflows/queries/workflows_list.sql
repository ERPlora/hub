-- Lista de workflows del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de WorkflowService.list_workflows. Los binds opcionales se pasan siempre:
--   :is_active = '' (sin filtro) | '0' | '1'   ;   :trigger_type = '' (sin filtro) | valor
SELECT id, name, description, trigger_type, trigger_config, conditions, actions,
       is_active, last_run_at, total_runs, created_at
FROM workflows_workflow
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:is_active = '' OR is_active = CAST(:is_active AS INTEGER))
  AND (:trigger_type = '' OR trigger_type = :trigger_type)
ORDER BY created_at DESC
LIMIT :limit;
