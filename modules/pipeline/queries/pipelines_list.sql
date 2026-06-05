-- Lista embudos del hub (opcionalmente solo activos). Runtime inyecta :hub_id.
-- Portado de PipelineService.list_pipelines. :active_only = 1 filtra a is_active=1.
SELECT id, name, description, is_default, is_active, color, "order", created_at
FROM pipeline_pipeline
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY "order" ASC, name ASC;
