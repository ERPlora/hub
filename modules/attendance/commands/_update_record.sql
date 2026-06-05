-- Primitiva de corrección de fichaje (emitida por el handler WASM update_record).
-- Runtime inyecta :hub_id, :current_user_id, :now. El handler valida que clock_out
-- no sea anterior a clock_in y recalcula :total_hours antes de emitir.
UPDATE attendance_record
SET clock_in      = :clock_in,
    clock_out     = :clock_out,
    break_minutes = :break_minutes,
    total_hours   = :total_hours,
    status        = :status,
    notes         = :notes,
    location      = :location,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :record_id AND hub_id = :hub_id AND is_deleted = 0;
