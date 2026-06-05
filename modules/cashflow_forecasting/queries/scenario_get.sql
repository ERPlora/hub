-- Un escenario por id (scope hub_id). Portado de CashflowService.get_or_error.
SELECT id, code, name, description, scenario_type, opening_balance, currency,
       is_active, parameters, created_at
FROM cashflow_forecasting_scenario
WHERE id = :scenario_id AND hub_id = :hub_id AND is_deleted = 0;
