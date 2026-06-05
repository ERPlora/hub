-- Primitiva de inserción de fichaje (emitida por el handler WASM clock_in).
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- El handler valida que no exista ya un fichaje abierto antes de emitir este insert.
INSERT INTO attendance_record
  (id, hub_id, employee_id, employee_name, clock_in, clock_out,
   break_minutes, total_hours, status, notes, location, device,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :employee_id, :employee_name, :clock_in, NULL,
   0, 0, :status, :notes, :location, :device,
   0, :current_user_id, :current_user_id, :now, :now);
