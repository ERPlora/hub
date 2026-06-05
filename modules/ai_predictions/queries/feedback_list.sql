-- Feedback de una predicción (scope hub_id), en orden cronológico de creación.
-- Portado de la parte de feedback de PredictionService.get_prediction.
SELECT id, prediction_id, actual_value, feedback_type, notes,
       recorded_at, created_at
FROM ai_predictions_feedback
WHERE prediction_id = :prediction_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
