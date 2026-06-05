-- Bloqueo lógico de un bin (dañado, mantenimiento). Runtime inyecta :current_user_id, :now.
-- Portado de LocationService.block_bin. El guard "ya bloqueado" lo cubre el WHERE
-- is_blocked = 0 (no toca filas si ya estaba bloqueado).
UPDATE locations_bin
SET is_blocked   = 1,
    block_reason = :reason,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :bin_id AND hub_id = :hub_id AND is_deleted = 0 AND is_blocked = 0;
