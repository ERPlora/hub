-- Lista deals con filtros opcionales por embudo/etapa/estado. Runtime inyecta :hub_id.
-- Portado de PipelineService.list_deals. Binds opcionales: '' = sin filtro para pipeline/stage;
-- :status = '' devuelve todos los estados. :limit acota el resultado.
SELECT id, pipeline_id, stage_id, deal_name, deal_value, customer_name,
       expected_close_date, status, entered_stage_at, won_at, lost_at, lost_reason
FROM pipeline_deal
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:pipeline_id = '' OR pipeline_id = :pipeline_id)
  AND (:stage_id    = '' OR stage_id    = :stage_id)
  AND (:status      = '' OR status      = :status)
ORDER BY created_at DESC
LIMIT :limit;
