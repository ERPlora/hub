-- Categorías del escaparate (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de StoreService.list_categories. :parent_id = '' → sin filtro de padre;
-- :is_published = -1 → sin filtro de publicación.
SELECT id, slug, name, parent_id, description, is_published, "order"
FROM online_store_category
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:parent_id = '' OR parent_id = :parent_id)
  AND (:is_published = -1 OR is_published = :is_published)
ORDER BY "order" ASC, name ASC;
