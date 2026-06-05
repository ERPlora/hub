-- Fichajes del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de TimeControlService.list_records. Los binds opcionales se pasan SIEMPRE:
-- '' = sin filtro (empleado, tipo, rango de fechas). :limit acota el nº de filas.
SELECT id, employee_id, employee_name, timestamp, record_type, method,
       workplace_id, is_within_geofence, notes
FROM time_control_clock_record
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:employee_id = '' OR employee_id = :employee_id)
  AND (:record_type = '' OR record_type = :record_type)
  AND (:date_from   = '' OR timestamp  >= :date_from)
  AND (:date_to     = '' OR timestamp  <= :date_to)
ORDER BY timestamp DESC
LIMIT :limit;
