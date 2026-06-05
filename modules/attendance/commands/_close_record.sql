-- Primitiva de cierre de fichaje (emitida por el handler WASM clock_out).
-- Runtime inyecta :hub_id, :current_user_id, :now.
-- :clock_out, :break_minutes y :total_hours los calcula el handler (delta - descanso).
UPDATE attendance_record
SET clock_out     = :clock_out,
    break_minutes = :break_minutes,
    total_hours   = :total_hours,
    notes         = :notes,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :record_id AND hub_id = :hub_id AND is_deleted = 0
  AND clock_out IS NULL;
