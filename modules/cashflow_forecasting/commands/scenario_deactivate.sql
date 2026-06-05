-- Desactivación lógica de un escenario (NO borra: lo saca de la selección activa).
-- Portado de CashflowService.deactivate_scenario. Runtime inyecta :hub_id,
-- :current_user_id, :now.
UPDATE cashflow_forecasting_scenario
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :scenario_id AND hub_id = :hub_id AND is_deleted = 0;
