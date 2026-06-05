-- Partes de horas de un contrato (scope hub_id). :only_unbilled = 1 filtra los no facturados.
-- line_total se calcula en el SDK/UI (hours * hourly_rate); aquí se devuelven los inputs.
SELECT id, contract_id, entry_date, hours, hourly_rate, employee_ref,
       description, is_invoiced, invoiced_at, created_at
FROM project_billing_time_entry
WHERE hub_id = :hub_id AND is_deleted = 0
  AND contract_id = :contract_id
  AND (:only_unbilled = 0 OR is_invoiced = 0)
ORDER BY entry_date ASC, created_at ASC;
