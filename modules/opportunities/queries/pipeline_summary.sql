-- Resumen del pipeline: nº de oportunidades y valor total por etapa.
-- Portado de OpportunityService.get_pipeline_summary. Runtime inyecta :hub_id.
-- El zero-fill de etapas sin oportunidades y los totales agregados los compone la UI/SDK.
SELECT stage,
       COUNT(id)            AS count,
       COALESCE(SUM(value), 0) AS total_value
FROM opportunities_opportunity
WHERE hub_id = :hub_id AND is_deleted = 0
GROUP BY stage;
