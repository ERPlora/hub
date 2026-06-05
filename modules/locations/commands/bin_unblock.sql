-- Desbloqueo de un bin. Runtime inyecta :current_user_id, :now.
-- Portado de LocationService.unblock_bin. El guard "no estaba bloqueado" lo cubre el
-- WHERE is_blocked = 1.
UPDATE locations_bin
SET is_blocked   = 0,
    block_reason = '',
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :bin_id AND hub_id = :hub_id AND is_deleted = 0 AND is_blocked = 1;
