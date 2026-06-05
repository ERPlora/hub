-- Cambia el estado/carpeta de un hilo (open/closed/archived/spam → folder coherente).
-- Transición simple (Tier 0). Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE communications_thread
SET status     = :status,
    folder     = :folder,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0;
