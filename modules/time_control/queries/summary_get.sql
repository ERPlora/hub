-- Resumen diario de un empleado para una fecha concreta (scope hub_id).
-- Portado de TimeControlService.get_daily_summary.
SELECT id, employee_id, employee_name, date, first_clock_in, last_clock_out,
       total_work_minutes, total_break_minutes, clock_count, is_complete
FROM time_control_daily_summary
WHERE hub_id = :hub_id AND is_deleted = 0
  AND employee_id = :employee_id
  AND date = :date;
