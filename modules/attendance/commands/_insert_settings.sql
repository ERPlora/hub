-- Primitiva de alta de la fila singleton de settings (cuando aún no existe).
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- El handler/runtime decide insertar (no hay fila) o actualizar (settings_update.sql).
INSERT INTO attendance_settings
  (id, hub_id, require_photo, allow_manual_entry, late_threshold_minutes,
   early_departure_minutes, auto_clock_out_hours,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :require_photo, :allow_manual_entry, :late_threshold_minutes,
   :early_departure_minutes, :auto_clock_out_hours,
   0, :current_user_id, :current_user_id, :now, :now);
