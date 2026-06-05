-- Modelos predictivos del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de PredictionService.list_models. :prediction_type = '' → sin filtro de tipo.
-- :active_only = 1 → solo activos; cualquier otro valor → todos.
SELECT id, code, name, prediction_type, entity_type, model_version,
       features, is_active, accuracy_score, trained_at, created_at
FROM ai_predictions_model
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:prediction_type = '' OR prediction_type = :prediction_type)
  AND (:active_only <> 1 OR is_active = 1)
ORDER BY code ASC;
