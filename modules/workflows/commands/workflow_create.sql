-- Alta de workflow. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de WorkflowService.create_workflow. La validación de trigger_type y de que
-- 'actions' sea lista no vacía con 'type' por acción la garantiza el JSON Schema; la
-- lógica de ejecución (evaluación de condiciones, generación de pasos) va a WASM —
-- ver WASM-TODO. trigger_config/conditions/actions se persisten como JSON TEXT.
INSERT INTO workflows_workflow
  (id, hub_id, name, description, trigger_type, trigger_config, conditions, actions,
   is_active, last_run_at, total_runs,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :trigger_type, :trigger_config, :conditions, :actions,
   :is_active, NULL, 0,
   0, :current_user_id, :current_user_id, :now, :now);
