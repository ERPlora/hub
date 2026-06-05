-- Nóminas del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de PayslipService.list_payslips. Filtros: '' = sin filtro en empleado/estado;
-- :period_from / :period_to vacíos = sin acotar por fechas.
SELECT id, employee_id, employee_name, period_start, period_end,
       gross_salary, total_earnings, total_deductions, net_salary,
       status, paid_date
FROM payroll_payslip
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:employee_id = '' OR employee_id = :employee_id)
  AND (:status      = '' OR status      = :status)
  AND (:period_from = '' OR period_start >= :period_from)
  AND (:period_to   = '' OR period_end   <= :period_to)
ORDER BY period_start DESC
LIMIT :limit;
