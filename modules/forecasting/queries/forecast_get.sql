-- Una ejecución de pronóstico por id (scope hub_id). Portado de get_forecast (cabecera).
-- Los puntos se obtienen aparte con forecasting.points.list.
SELECT id, model_id, forecast_number, forecast_horizon_periods, period_unit,
       generated_at, generated_by_ref, status, accuracy_score, notes, created_at
FROM forecasting_forecast
WHERE id = :forecast_id AND hub_id = :hub_id AND is_deleted = 0;
