-- Ejecuciones de pronóstico recientes (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ForecastingService.list_forecasts. Filtros: :model_id ('' = sin filtro),
-- :status ('' = sin filtro). :limit limita el nº de filas devueltas.
SELECT id, model_id, forecast_number, forecast_horizon_periods, period_unit,
       generated_at, generated_by_ref, status, accuracy_score, notes, created_at
FROM forecasting_forecast
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:model_id = '' OR model_id = :model_id)
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
