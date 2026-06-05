-- Invalidación total de la caché de un cubo: soft-delete de todos sus slices cacheados.
-- Portado de OLAPService.invalidate_cube_cache (que borraba en duro; en hub-next es soft-delete
-- por el contrato §2.5). Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE olap_cubes_cached_slice
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE cube_id = :cube_id AND hub_id = :hub_id AND is_deleted = 0;
