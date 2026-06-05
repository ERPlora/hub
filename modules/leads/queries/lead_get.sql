-- Un lead por id (scope hub_id). Portado de LeadService.get_lead.
SELECT id, lead_number, first_name, last_name, email, phone, company, job_title,
       source_id, status, assigned_to_ref, estimated_value, notes,
       contacted_at, qualified_at, converted_at, created_at
FROM leads_lead
WHERE id = :lead_id AND hub_id = :hub_id AND is_deleted = 0;
