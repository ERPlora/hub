-- Lista de fichajes del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de AttendanceService.list_records. Filtros opcionales por empleado, estado
-- y rango de fechas sobre clock_in ('' = sin filtro). El recorte de :limit lo aplica
-- el SDK/UI; aquí ordenamos por clock_in descendente.
SELECT id, employee_id, employee_name, clock_in, clock_out,
       break_minutes, total_hours, status, notes, location, device
FROM attendance_record
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:employee_id = '' OR employee_id = :employee_id)
  AND (:status      = '' OR status      = :status)
  AND (:date_from   = '' OR clock_in   >= :date_from)
  AND (:date_to     = '' OR clock_in   <= :date_to)
ORDER BY clock_in DESC;
