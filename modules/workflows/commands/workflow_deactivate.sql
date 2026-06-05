-- Marca un workflow como inactivo. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de WorkflowService.deactivate_workflow.
UPDATE workflows_workflow
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :workflow_id AND hub_id = :hub_id AND is_deleted = 0;
