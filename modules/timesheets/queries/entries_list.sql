-- Lista de registros de tiempo del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de TimesheetService.list_entries. Los filtros vacíos ('') se ignoran;
-- :billable acepta -1 (= sin filtro), 0 o 1. Orden por fecha descendente.
SELECT id, employee_id, employee_name, date, start_time, end_time,
       duration_minutes, description, status, billable, project_name,
       client_name, hourly_rate_id, rate_amount, approved_by, approved_at
FROM timesheets_time_entry
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:employee_id = '' OR employee_id = :employee_id)
  AND (:status = '' OR status = :status)
  AND (:date_from = '' OR date >= :date_from)
  AND (:date_to = '' OR date <= :date_to)
  AND (:project_name = '' OR project_name LIKE '%' || :project_name || '%')
  AND (:billable = -1 OR billable = :billable)
ORDER BY date DESC
LIMIT :limit;
