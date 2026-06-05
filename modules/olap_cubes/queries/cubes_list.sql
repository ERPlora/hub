-- Lista de cubos OLAP del hub. Runtime inyecta :hub_id.
-- Portado de OLAPService.list_cubes (active_only por defecto). El bind :active_only
-- controla el filtro: '1' = solo activos, '' = todos. Orden por code ascendente.
SELECT id, code, name, description, source_table,
       dimensions, measures, filters, is_active, created_at
FROM olap_cubes_cube
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY code ASC;
