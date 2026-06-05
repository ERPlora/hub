-- Mapeos de producto Glovo->local de una tienda. Runtime inyecta :hub_id.
-- Bind :store_id obligatorio (los productos siempre se listan por tienda).
SELECT id, store_id, glovo_product_id, local_product_ref, name, price,
       is_available, last_synced_at
FROM glovo_product
WHERE hub_id = :hub_id AND is_deleted = 0 AND store_id = :store_id
ORDER BY name ASC;
