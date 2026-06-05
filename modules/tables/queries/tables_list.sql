-- Lista de mesas del hub con nombre de zona. Runtime inyecta :hub_id.
-- Portado de TableService.list_tables (orden por número de mesa).
SELECT t.id, t.number, t.name, t.capacity, t.shape, t.status, t.is_active,
       t.position_x, t.position_y, t.width, t.height,
       t.zone_id, z.name AS zone
FROM tables_table t
LEFT JOIN tables_zone z ON z.id = t.zone_id AND z.is_deleted = 0
WHERE t.hub_id = :hub_id AND t.is_deleted = 0
ORDER BY t.number ASC;
