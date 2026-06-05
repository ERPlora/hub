-- Alta de plantilla de prompt. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de AIReportService.create_template. El code único por hub lo garantiza el índice
-- ix_ai_reports_template_hub_code (rechazo de duplicado). default_data_sources llega como
-- JSON string ('[]' por defecto). output_format por defecto 'markdown'.
INSERT INTO ai_reports_template
  (id, hub_id, code, name, description, prompt_template,
   default_data_sources, output_format, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :prompt_template,
   :default_data_sources, :output_format, 1,
   0, :current_user_id, :current_user_id, :now, :now);
