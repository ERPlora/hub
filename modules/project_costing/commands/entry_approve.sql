-- Aprobación de entrada de coste: pending → approved. Runtime inyecta :current_user_id, :now, :hub_id.
-- Portado de ProjectCostingService.approve_cost_entry. El guard de estado (solo pending
-- puede aprobarse) se materializa en la cláusula status='pending'; 0 filas afectadas →
-- el runtime devuelve invalid_state.
UPDATE project_costing_entry
SET status = 'approved',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :entry_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
