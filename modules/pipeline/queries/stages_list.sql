-- Etapas de un embudo, ordenadas. Runtime inyecta :hub_id.
-- Portado de PipelineService.get_pipeline (parte de stages).
SELECT id, pipeline_id, code, name, "order", probability_default,
       is_won, is_lost, color
FROM pipeline_stage
WHERE hub_id = :hub_id AND is_deleted = 0
  AND pipeline_id = :pipeline_id
ORDER BY "order" ASC;
