-- Almacenes del hub. Runtime inyecta :hub_id.
-- Portado de MultiWarehouseService.list_warehouses. :active_only ('1' = solo activos,
-- '' o '0' = todos). Orden: por defecto primero, luego por código.
SELECT id, code, name, address, type, is_active, is_default, owner_organization_ref
FROM multi_warehouse_warehouse
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR :active_only = '0' OR is_active = 1)
ORDER BY is_default DESC, code ASC;
