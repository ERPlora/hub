-- Alta de escenario de cash-flow. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de CashflowService.create_scenario.
-- La validación de scenario_type / opening_balance / parameters (JSON) la hace
-- el JSON Schema; (hub_id, code) único lo garantiza ix_cf_scenario_hub_code.
INSERT INTO cashflow_forecasting_scenario
  (id, hub_id, code, name, description, scenario_type, opening_balance, currency,
   is_active, parameters, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :scenario_type, :opening_balance,
   :currency, 1, :parameters, 0, :current_user_id, :current_user_id, :now, :now);
