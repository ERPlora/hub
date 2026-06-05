-- Predicciones recientes del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de PredictionService.list_predictions. :model_id = '' → sin filtro de modelo;
-- :entity_ref = '' → sin filtro de entidad. :limit acota el nº de filas devueltas.
SELECT id, model_id, entity_ref, prediction_value, confidence,
       predicted_at, features_used, explanation, created_at
FROM ai_predictions_prediction
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:model_id   = '' OR model_id   = :model_id)
  AND (:entity_ref = '' OR entity_ref = :entity_ref)
ORDER BY created_at DESC
LIMIT :limit;
