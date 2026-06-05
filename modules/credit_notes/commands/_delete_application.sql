-- Sub-paso del handler WASM unapply: soft-delete de una aplicación.
-- (El legacy hace delete duro; en hub-next preferimos soft-delete + audit, §2.5.)
UPDATE credit_notes_application
SET is_deleted = 1, deleted_at = :now,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :application_id AND hub_id = :hub_id AND is_deleted = 0;
