-- Alta de modelo predictivo. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PredictionService.create_model. La normalización de features y la validación
-- de prediction_type (enum) la hace el schema JSON; la unicidad de code por hub la
-- garantiza el índice uq_ai_pred_model_hub_code. :features ya viene como string JSON.
INSERT INTO ai_predictions_model
  (id, hub_id, code, name, prediction_type, entity_type, model_version,
   features, is_active, accuracy_score, trained_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :prediction_type, :entity_type, :model_version,
   :features, 1, NULL, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
