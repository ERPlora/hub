-- Cierre de presupuesto: active → closed. Runtime inyecta :current_user_id, :now, :hub_id.
-- Portado de ProjectCostingService.close_budget. El guard de estado (solo active puede
-- cerrarse) se materializa en la cláusula status='active'; si la fila no está en active,
-- 0 filas afectadas → el runtime devuelve invalid_state.
UPDATE project_costing_budget
SET status = 'closed',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :budget_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'active';
