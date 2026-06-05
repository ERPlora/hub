-- Primitiva interna: inserta una solicitud ya calculada por el handler WASM.
-- El WASM resuelve days_count (días hábiles o 0.5 medio día), valida la fecha mínima
-- contra leave_settings y el saldo disponible; aquí solo se persiste el resultado.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO leave_request
  (id, hub_id, employee_id, employee_name, leave_type_id, start_date, end_date,
   days_count, is_half_day, half_day_period, status, reason, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :employee_id, :employee_name, :leave_type_id, :start_date, :end_date,
   :days_count, :is_half_day, :half_day_period, 'pending', :reason, '',
   0, :current_user_id, :current_user_id, :now, :now);
