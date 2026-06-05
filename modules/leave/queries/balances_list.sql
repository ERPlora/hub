-- Saldos de ausencias de un empleado para un año. Runtime inyecta :hub_id.
-- Portado de LeaveService.get_balance. remaining_days se calcula en SQL (entitled+carried-used-pending).
SELECT b.id, b.employee_id, b.employee_name, b.leave_type_id,
       t.name AS leave_type_name, b.year,
       b.entitled_days, b.used_days, b.pending_days, b.carried_over,
       (b.entitled_days + b.carried_over - b.used_days - b.pending_days) AS remaining_days
FROM leave_balance b
LEFT JOIN leave_type t ON t.id = b.leave_type_id AND t.hub_id = b.hub_id
WHERE b.hub_id = :hub_id AND b.is_deleted = 0
  AND b.employee_id = :employee_id
  AND b.year = :year
ORDER BY t.name ASC;
