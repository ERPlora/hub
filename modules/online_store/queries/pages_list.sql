-- Páginas CMS del escaparate (con filtro opcional de publicación). Runtime inyecta :hub_id.
-- Portado de StoreService.list_pages / routes.list_pages. :is_published = -1 → sin filtro.
SELECT id, slug, title, content_html, is_published, order_in_menu
FROM online_store_page
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:is_published = -1 OR is_published = :is_published)
ORDER BY order_in_menu ASC, title ASC;
