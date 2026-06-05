-- Conexiones de marketplace del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de MarketplaceService.list_connections. NOTA: credentials se devuelve crudo aquí;
-- el enmascarado de credenciales (ver WASM-TODO) lo aplica el handler/serializador antes de
-- exponerlo al cliente. La UI NO debe mostrar credentials sin enmascarar.
-- Binds opcionales: :platform ('' = sin filtro), :active_only (1 = solo activas, 0 = todas).
SELECT id, code, platform, name, is_active, region,
       last_sync_at, last_sync_status, created_at
FROM marketplaces_connection
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:platform = '' OR platform = :platform)
  AND (:active_only = 0 OR is_active = 1)
ORDER BY created_at DESC;
