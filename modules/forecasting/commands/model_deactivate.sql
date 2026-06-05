-- Desactivación lógica de un modelo de pronóstico (is_active = 0; NO lo borra).
-- Portado de ForecastingService.deactivate_model. El estado "ya inactivo" lo detecta
-- el runtime/UI por la query previa; aquí solo aplicamos el cambio.
UPDATE forecasting_model
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :model_id AND hub_id = :hub_id AND is_deleted = 0;
