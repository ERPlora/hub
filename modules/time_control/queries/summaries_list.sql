-- Resúmenes diarios del hub para informes, con filtros opcionales por empleado y rango.
-- Runtime inyecta :hub_id. Binds opcionales: '' = sin filtro. :limit acota las filas.
SELECT id, employee_id, employee_name, date, first_clock_in, last_clock_out,
       total_work_minutes, total_break_minutes, clock_count, is_complete
FROM time_control_daily_summary
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:employee_id = '' OR employee_id = :employee_id)
  AND (:date_from   = '' OR date >= :date_from)
  AND (:date_to     = '' OR date <= :date_to)
ORDER BY date DESC, employee_name ASC
LIMIT :limit;
