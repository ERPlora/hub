-- Alta de modelo de pronóstico. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ForecastingService.create_model. La validación de model_type/target_metric
-- (enum) la garantiza el JSON Schema; code único por hub lo garantiza el índice
-- ix_forecasting_model_hub_code.
INSERT INTO forecasting_model
  (id, hub_id, code, name, model_type, target_metric, parameters,
   training_period_days, is_active, last_trained_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :model_type, :target_metric, :parameters,
   :training_period_days, 1, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
