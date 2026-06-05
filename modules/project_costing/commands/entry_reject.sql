-- Rechazo de entrada de coste: pending → rejected. Runtime inyecta :current_user_id, :now, :hub_id.
-- Portado de ProjectCostingService.reject_cost_entry. El guard de estado (solo pending
-- puede rechazarse) se materializa en la cláusula status='pending'; 0 filas afectadas →
-- el runtime devuelve invalid_state. reason (obligatorio) lo valida el JSON Schema.
-- El append del rastro "[REJECTED] reason" a notes (no expresable de forma portable en
-- una sola sentencia con timestamp) se documenta en WASM-TODO; aquí persistimos reason.
UPDATE project_costing_entry
SET status = 'rejected',
    notes = TRIM(COALESCE(notes, '') || char(10) || '[REJECTED] ' || :reason),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :entry_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
