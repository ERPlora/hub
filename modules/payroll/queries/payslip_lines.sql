-- Líneas (devengos/deducciones) de una nómina. Runtime inyecta :hub_id.
-- Portado del bloque de líneas de PayslipService.get_payslip_detail.
SELECT id, payslip_id, concept_name, type, amount, is_percentage,
       percentage, base_amount, quantity, rate, source_module, source_id, sort_order
FROM payroll_payslip_line
WHERE hub_id = :hub_id AND is_deleted = 0 AND payslip_id = :payslip_id
ORDER BY sort_order ASC;
