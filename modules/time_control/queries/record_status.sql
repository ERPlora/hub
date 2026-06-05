-- Último fichaje de un empleado (scope hub_id). Portado de TimeControlService.get_clock_status:
-- el SDK/UI deriva clocked_in = (record_type == 'clock_in') a partir de esta fila.
SELECT id, employee_id, employee_name, timestamp, record_type, method, workplace_id
FROM time_control_clock_record
WHERE hub_id = :hub_id AND is_deleted = 0
  AND employee_id = :employee_id
ORDER BY timestamp DESC
LIMIT 1;
