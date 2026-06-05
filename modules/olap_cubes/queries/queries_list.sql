-- Ejecuciones recientes de consultas OLAP del hub. Runtime inyecta :hub_id.
-- Portado de OLAPService.list_queries. Filtro opcional por cubo (:cube_id = '' = sin filtro).
-- El límite lo aplica el SDK/UI; aquí ordenamos por fecha de ejecución descendente.
SELECT id, cube_id, query_number, dimensions_used, measures_used,
       filters_applied, result_count, executed_at, executed_by_ref,
       execution_time_ms
FROM olap_cubes_query
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:cube_id = '' OR cube_id = :cube_id)
ORDER BY executed_at DESC;
