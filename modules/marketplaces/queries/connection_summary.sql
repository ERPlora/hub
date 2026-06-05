-- Snapshot de una conexión: datos de cabecera + contadores agregados. Runtime inyecta :hub_id.
-- Portado de MarketplaceService.get_connection_summary. Devuelve la conexión con el nº de
-- mappings y de orders asociados. (El último sync se consulta aparte con marketplaces.syncs.list
-- filtrando por connection_id; aquí solo agregamos los contadores en una fila.)
SELECT c.id, c.code, c.platform, c.name, c.is_active, c.region,
       c.last_sync_at, c.last_sync_status, c.created_at,
       (SELECT COUNT(*) FROM marketplaces_product_mapping m
          WHERE m.hub_id = c.hub_id AND m.connection_id = c.id AND m.is_deleted = 0) AS mappings_count,
       (SELECT COUNT(*) FROM marketplaces_order o
          WHERE o.hub_id = c.hub_id AND o.connection_id = c.id AND o.is_deleted = 0) AS orders_count
FROM marketplaces_connection c
WHERE c.hub_id = :hub_id AND c.is_deleted = 0 AND c.id = :connection_id;
