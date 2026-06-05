-- Historial de ejecuciones del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de WorkflowService.list_runs. Binds opcionales (se pasan siempre):
--   :workflow_id = '' (sin filtro) | uuid    ;   :status = '' (sin filtro) | running|completed|failed|cancelled
SELECT id, workflow_id, status, started_at, completed_at,
       input_data, output_data, error_message, created_at
FROM workflows_run
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:workflow_id = '' OR workflow_id = :workflow_id)
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
