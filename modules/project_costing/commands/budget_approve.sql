-- Aprobación de presupuesto: draft → active. Runtime inyecta :current_user_id, :now, :hub_id.
-- Portado de ProjectCostingService.approve_budget. El guard de estado (solo draft
-- puede aprobarse) se materializa aquí en la cláusula status='draft'; si la fila no
-- está en draft, 0 filas afectadas → el runtime devuelve invalid_state.
UPDATE project_costing_budget
SET status = 'active',
    approved_by_ref = :current_user_id,
    approved_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :budget_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
