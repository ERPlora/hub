-- Alta de página CMS del escaparate. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de StoreService.create_page. El slug único por hub lo garantiza el índice.
-- Se crea sin publicar (is_published = 0).
INSERT INTO online_store_page
  (id, hub_id, slug, title, content_html, is_published, order_in_menu,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :slug, :title, :content_html, 0, 0,
   0, :current_user_id, :current_user_id, :now, :now);
