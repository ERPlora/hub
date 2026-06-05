-- Desactivación lógica de un modelo (NO borra: solo lo saca de futuras predicciones).
-- Portado de PredictionService.deactivate_model. La guarda "ya estaba inactivo" se
-- comprueba en el SDK/UI; aquí solo aplicamos el cambio sobre filas activas.
UPDATE ai_predictions_model
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :model_id AND hub_id = :hub_id AND is_deleted = 0;
