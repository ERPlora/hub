-- Directorio de proveedores. Runtime inyecta :hub_id.
-- Portado de PurchaseOrderService.list_suppliers (active_only + búsqueda opcional).
-- :active_only = 1 limita a activos; :search = '' no filtra texto.
SELECT
    id        AS id,
    name      AS name,
    tax_id    AS tax_id,
    email     AS email,
    phone     AS phone,
    is_active AS is_active
FROM purchase_orders_supplier
WHERE hub_id = :hub_id
  AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
  AND (
        :search = ''
        OR name LIKE '%' || :search || '%'
        OR email LIKE '%' || :search || '%'
        OR tax_id LIKE '%' || :search || '%'
      )
ORDER BY name ASC;
