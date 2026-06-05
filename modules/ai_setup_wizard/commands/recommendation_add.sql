-- Alta de recomendación emitida por la IA atada a una sesión.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de SetupWizardService.add_recommendation. La validación de category/priority
-- (enum) la garantiza el JSON Schema; la existencia de la sesión la valida el runtime.
INSERT INTO ai_setup_wizard_recommendation
  (id, hub_id, session_id, category, title, description, priority,
   is_applied, applied_at, related_module_id,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :session_id, :category, :title, :description, :priority,
   0, NULL, :related_module_id,
   0, :current_user_id, :current_user_id, :now, :now);
