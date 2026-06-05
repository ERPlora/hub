-- Un embudo por id (scope hub_id). Portado de PipelineService.get_pipeline (cabecera).
-- Las etapas y deals se piden con queries separadas (pipeline.stages.list / pipeline.deals.list).
SELECT id, name, description, is_default, is_active, color, "order", created_at
FROM pipeline_pipeline
WHERE id = :pipeline_id AND hub_id = :hub_id AND is_deleted = 0;
