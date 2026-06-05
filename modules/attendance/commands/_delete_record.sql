-- Borrado lógico de un fichaje (emitido por el handler WASM delete_record).
-- Runtime inyecta :hub_id, :current_user_id, :now. El handler rechaza borrar un
-- fichaje ABIERTO (clock_out IS NULL) antes de emitir este soft-delete.
UPDATE attendance_record
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :record_id AND hub_id = :hub_id AND is_deleted = 0;
