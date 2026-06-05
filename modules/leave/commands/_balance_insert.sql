-- Primitiva interna: inserta un saldo nuevo (rama "no existía" del upsert de set_balance).
-- El handler WASM decide insertar vs. actualizar tras leer balances_list por la clave
-- (employee_id, leave_type_id, year). Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO leave_balance
  (id, hub_id, employee_id, employee_name, leave_type_id, year,
   entitled_days, used_days, pending_days, carried_over,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :employee_id, :employee_name, :leave_type_id, :year,
   :entitled_days, 0.0, 0.0, :carried_over,
   0, :current_user_id, :current_user_id, :now, :now);
