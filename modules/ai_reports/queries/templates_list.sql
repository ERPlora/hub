-- Plantillas de informe del hub. Runtime inyecta :hub_id.
-- Portado de AIReportService.list_templates. :active_only ('1'=solo activas, ''=todas)
-- lo decide el SDK/UI; aquí filtramos por is_active cuando se pide.
SELECT id, code, name, description, prompt_template,
       default_data_sources, output_format, is_active, created_at
FROM ai_reports_template
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY name ASC;
