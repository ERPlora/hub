-- Modelos de pronóstico del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ForecastingService.list_models. Filtros opcionales: :active_only (1=solo
-- activos, 0=todos) y :target_metric ('' = sin filtro).
SELECT id, code, name, model_type, target_metric, parameters,
       training_period_days, is_active, last_trained_at, created_at
FROM forecasting_model
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
  AND (:target_metric = '' OR target_metric = :target_metric)
ORDER BY code ASC;
