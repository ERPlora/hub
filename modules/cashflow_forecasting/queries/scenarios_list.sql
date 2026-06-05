-- Escenarios de cash-flow del hub. Runtime inyecta :hub_id.
-- Portado de CashflowService.list_scenarios. :active_only ('1' = solo activos,
-- '' = todos) lo pasa el SDK/UI.
SELECT id, code, name, description, scenario_type, opening_balance, currency,
       is_active, parameters, created_at
FROM cashflow_forecasting_scenario
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY code ASC;
