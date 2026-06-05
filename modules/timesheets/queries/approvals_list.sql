-- Lotes de aprobación de periodos del hub con filtros opcionales. Runtime inyecta :hub_id.
-- :employee_id y :status vacíos ('') se ignoran. Orden por inicio de periodo descendente.
SELECT id, employee_id, employee_name, period_start, period_end, status,
       approved_by, approved_at, total_hours, billable_hours, notes
FROM timesheets_approval
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:employee_id = '' OR employee_id = :employee_id)
  AND (:status = '' OR status = :status)
ORDER BY period_start DESC
LIMIT :limit;
