-- Actualización de plantilla. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de AIReportService.update_template. El legacy aceptaba un subconjunto arbitrario
-- de campos; aquí se actualizan los campos editables de forma fija (name, description,
-- prompt_template, default_data_sources [JSON string], output_format, is_active).
-- El SDK/UI envía SIEMPRE los 6 campos (precargados con los valores actuales si no cambian).
UPDATE ai_reports_template
SET name                 = :name,
    description          = :description,
    prompt_template      = :prompt_template,
    default_data_sources = :default_data_sources,
    output_format        = :output_format,
    is_active            = :is_active,
    updated_by           = :current_user_id,
    updated_at           = :now
WHERE id = :template_id AND hub_id = :hub_id AND is_deleted = 0;
