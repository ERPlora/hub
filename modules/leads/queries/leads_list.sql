-- Lista de leads del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de LeadService.list_leads. Los binds :status, :source_id y :assigned_to
-- deben pasarse: '' = sin filtro. Orden por fecha de creación descendente.
SELECT id, lead_number, first_name, last_name, email, phone, company, job_title,
       source_id, status, assigned_to_ref, estimated_value, notes,
       contacted_at, qualified_at, converted_at, created_at
FROM leads_lead
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status      = '' OR status          = :status)
  AND (:source_id   = '' OR source_id       = :source_id)
  AND (:assigned_to = '' OR assigned_to_ref = :assigned_to)
ORDER BY created_at DESC
LIMIT :limit;
