-- Tiendas Glovo del hub. Runtime inyecta :hub_id. Portado de GlovoService.list_stores.
-- :active_only = 1 filtra solo activas; '' o 0 las muestra todas.
SELECT id, store_id, name, country, city, glovo_status, is_active,
       last_sync_at, settings, created_at
FROM glovo_store
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR :active_only = 0 OR is_active = 1)
ORDER BY name ASC;
