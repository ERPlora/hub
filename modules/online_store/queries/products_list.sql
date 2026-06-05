-- Productos del escaparate (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de StoreService.list_products / routes.list_products. El filtro is_published
-- usa -1 como "sin filtro" (0=no publicados, 1=publicados). :search = '' → sin búsqueda.
SELECT id, product_ref, slug, name, short_description, description,
       price, sale_price, stock_quantity, sku, images, is_published,
       seo_title, seo_description, weight, dimensions
FROM online_store_product
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:is_published = -1 OR is_published = :is_published)
  AND (:search = '' OR LOWER(name) LIKE '%' || LOWER(:search) || '%')
ORDER BY created_at DESC;
