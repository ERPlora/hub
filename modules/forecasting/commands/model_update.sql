-- Actualización de campos de un modelo de pronóstico. Runtime inyecta :current_user_id, :now.
-- Portado de ForecastingService.update_model. El esquema fija los campos admitidos; los
-- binds opcionales no aportados se envían con su valor actual desde el SDK/UI.
UPDATE forecasting_model
SET name                 = :name,
    model_type           = :model_type,
    target_metric        = :target_metric,
    parameters           = :parameters,
    training_period_days = :training_period_days,
    is_active            = :is_active,
    updated_by           = :current_user_id,
    updated_at           = :now
WHERE id = :model_id AND hub_id = :hub_id AND is_deleted = 0;
