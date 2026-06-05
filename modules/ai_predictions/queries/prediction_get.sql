-- Una predicción por id (scope hub_id). Portado de PredictionService.get_prediction
-- (la cabecera; el feedback asociado se obtiene con ai_predictions.feedback.list).
SELECT id, model_id, entity_ref, prediction_value, confidence,
       predicted_at, features_used, explanation, created_at
FROM ai_predictions_prediction
WHERE id = :prediction_id AND hub_id = :hub_id AND is_deleted = 0;
