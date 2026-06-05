-- Desactivación lógica de un cubo (NO borra: lo saca de futuras selecciones y bloquea queries).
-- Portado de OLAPService.deactivate_cube. El chequeo "ya inactivo" lo resuelve el runtime
-- (lectura previa); aquí solo marcamos is_active = 0.
UPDATE olap_cubes_cube
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :cube_id AND hub_id = :hub_id AND is_deleted = 0;
