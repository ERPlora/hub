-- Menús publicados en Uber, opcionalmente filtrados por tienda. Runtime inyecta :hub_id.
-- Portado de UberEatsService.list_menus. Bind :store_id ('' = sin filtro).
SELECT id, store_id, uber_menu_id, name, items_count, last_synced_at, sync_status
FROM uber_eats_menu
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:store_id = '' OR store_id = :store_id)
ORDER BY name ASC;
