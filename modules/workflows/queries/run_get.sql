-- Una ejecución por id (scope hub_id). Portado de WorkflowService.get_run (cabecera).
-- Los pasos asociados se obtienen aparte con workflows.steps.list (:run_id).
SELECT id, workflow_id, status, started_at, completed_at,
       input_data, output_data, error_message, created_at
FROM workflows_run
WHERE id = :run_id AND hub_id = :hub_id AND is_deleted = 0;
