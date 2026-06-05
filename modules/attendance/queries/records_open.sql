-- Fichaje abierto (sin clock_out) de un empleado. Runtime inyecta :hub_id.
-- Usado por el handler clock_in/clock_out para comprobar si ya hay sesión abierta.
SELECT id, employee_id, employee_name, clock_in, clock_out,
       break_minutes, total_hours, status, notes, location, device
FROM attendance_record
WHERE hub_id = :hub_id AND is_deleted = 0
  AND employee_id = :employee_id
  AND clock_out IS NULL
ORDER BY clock_in DESC
LIMIT 1;
