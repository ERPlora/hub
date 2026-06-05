-- Una ficha de producto por su slug de escaparate (scope hub_id).
-- Portado de StoreService.get_product.
SELECT id, product_ref, slug, name, short_description, description,
       price, sale_price, stock_quantity, sku, images, is_published,
       seo_title, seo_description, weight, dimensions
FROM online_store_product
WHERE hub_id = :hub_id AND is_deleted = 0 AND slug = :slug
LIMIT 1;
