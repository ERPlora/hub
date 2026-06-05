-- Un modelo de pronóstico por id (scope hub_id). Portado de get_or_error(ForecastModel).
SELECT id, code, name, model_type, target_metric, parameters,
       training_period_days, is_active, last_trained_at, created_at
FROM forecasting_model
WHERE id = :model_id AND hub_id = :hub_id AND is_deleted = 0;
