-- Bins con filtros opcionales por zona y/o bloqueados. Runtime inyecta :hub_id.
-- Portado de LocationService.list_bins. (:zone_id = '' → sin filtro de zona;
-- :blocked_only = '1' → solo bloqueados, '' → todos.) Límite aplicado por el SDK/UI.
SELECT id, zone_id, warehouse_id, code, barcode, capacity,
       is_active, is_blocked, block_reason, created_at
FROM locations_bin
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:zone_id = '' OR zone_id = :zone_id)
  AND (:blocked_only = '' OR is_blocked = 1)
ORDER BY code ASC;
