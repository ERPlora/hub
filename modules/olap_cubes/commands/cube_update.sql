-- Actualización de un cubo OLAP. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de OLAPService.update_cube. La validación de aggs y la unicidad de code al renombrar
-- las garantiza el schema + el índice ix_olap_cube_hub_code. :dimensions/:measures/:filters
-- llegan serializados como JSON. is_active se normaliza a 0/1 en el payload.
UPDATE olap_cubes_cube
SET code         = :code,
    name         = :name,
    description  = :description,
    source_table = :source_table,
    dimensions   = :dimensions,
    measures     = :measures,
    filters      = :filters,
    is_active    = :is_active,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :cube_id AND hub_id = :hub_id AND is_deleted = 0;
