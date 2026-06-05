-- Añade una etapa a un embudo existente. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PipelineService.add_stage. La validación de que :pipeline_id existe y pertenece
-- al hub la hace el runtime antes de ejecutar (FK + scope hub_id).
INSERT INTO pipeline_stage
  (id, hub_id, pipeline_id, code, name, "order", probability_default,
   is_won, is_lost, color,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :pipeline_id, :code, :name, :order, :probability_default,
   :is_won, :is_lost, :color,
   0, :current_user_id, :current_user_id, :now, :now);
