-- Oportunidades del hub (pipeline) con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de OpportunityService.list_opportunities.
-- Los binds :stage y :assigned_to deben pasarse: '' = sin filtro.
-- weighted_value (value * probability/100) lo calcula la UI/SDK; aquí devolvemos los campos crudos.
SELECT id, opp_number, customer_name, customer_email, value, probability,
       expected_close_date, stage, close_reason, assigned_to_ref, notes,
       created_at
FROM opportunities_opportunity
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:stage       = '' OR stage           = :stage)
  AND (:assigned_to = '' OR assigned_to_ref = :assigned_to)
ORDER BY created_at DESC
LIMIT :limit;
