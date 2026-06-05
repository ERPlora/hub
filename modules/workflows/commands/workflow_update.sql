-- Edición de campos mutables de un workflow. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de WorkflowService.update_workflow. El UI/SDK envía SIEMPRE los campos
-- editables (name/description/trigger_type/trigger_config/conditions/actions/is_active),
-- precargados con los valores actuales para no machacar lo no tocado.
UPDATE workflows_workflow
SET name           = :name,
    description    = :description,
    trigger_type   = :trigger_type,
    trigger_config = :trigger_config,
    conditions     = :conditions,
    actions        = :actions,
    is_active      = :is_active,
    updated_by     = :current_user_id,
    updated_at     = :now
WHERE id = :workflow_id AND hub_id = :hub_id AND is_deleted = 0;
