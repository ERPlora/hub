-- Detalle de una nómina. Runtime inyecta :hub_id. Portado de PayslipService.get_payslip_detail
-- (las líneas se leen aparte con payroll.payslips.lines).
SELECT id, employee_id, employee_name, period_start, period_end,
       gross_salary, total_earnings, total_deductions, net_salary,
       status, paid_date, payment_method, notes, breakdown
FROM payroll_payslip
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :payslip_id;
