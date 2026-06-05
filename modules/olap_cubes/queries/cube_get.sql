-- Detalle de un cubo OLAP por id. Runtime inyecta :hub_id.
-- Portado del get_or_error de OLAPService (lectura de un cubo concreto del hub).
SELECT id, code, name, description, source_table,
       dimensions, measures, filters, is_active, created_at
FROM olap_cubes_cube
WHERE id = :cube_id AND hub_id = :hub_id AND is_deleted = 0;
