-- Un workflow por id (scope hub_id). Portado de WorkflowService.get_workflow.
SELECT id, name, description, trigger_type, trigger_config, conditions, actions,
       is_active, last_run_at, total_runs, created_at, updated_at
FROM workflows_workflow
WHERE id = :workflow_id AND hub_id = :hub_id AND is_deleted = 0;
