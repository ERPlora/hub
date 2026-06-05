-- Alta de un parte de horas imputado a un contrato. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de ProjectBillingService.log_time.
-- NOTA: el default de hourly_rate = tarifa del contrato cuando viene vacío, y la guarda hours>0,
-- las resuelve el SDK/UI (o el handler WASM si se prefiere server-side) antes de invocar este
-- comando; aquí se persisten los valores ya resueltos. Ver WASM-TODO §opcional.
INSERT INTO project_billing_time_entry
  (id, hub_id, contract_id, entry_date, hours, hourly_rate, employee_ref,
   description, is_invoiced, invoiced_at, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :contract_id, :entry_date, :hours, :hourly_rate, :employee_ref,
   :description, 0, NULL, 0, :current_user_id, :current_user_id, :now, :now);
