-- Alta de una nómina manual en borrador. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PayslipService.create_payslip. La validación (gross > 0, period_start <= period_end)
-- la garantiza el JSON Schema + el runtime; net_salary arranca = gross_salary (sin líneas todavía).
-- El cálculo automático con líneas (collectors, deducciones, balance) va a WASM — ver WASM-TODO.md.
INSERT INTO payroll_payslip
  (id, hub_id, employee_id, employee_name, period_start, period_end,
   gross_salary, total_earnings, total_deductions, net_salary, status,
   paid_date, payment_method, notes, breakdown,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :employee_id, :employee_name, :period_start, :period_end,
   :gross_salary, 0, 0, :gross_salary, 'draft',
   NULL, NULL, :notes, '{}',
   0, :current_user_id, :current_user_id, :now, :now);
