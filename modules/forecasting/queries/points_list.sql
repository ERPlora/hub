-- Puntos (valores predichos por periodo) de una ejecución de pronóstico. Runtime inyecta :hub_id.
-- Portado de get_forecast (puntos) / compare_forecast_to_actual (lectura base).
SELECT id, forecast_id, period_start, period_end, predicted_value,
       lower_bound, upper_bound, confidence
FROM forecasting_point
WHERE forecast_id = :forecast_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY period_start ASC;
