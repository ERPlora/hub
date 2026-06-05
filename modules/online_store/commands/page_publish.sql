-- Publica una página CMS del escaparate. Runtime inyecta :current_user_id, :now.
-- Portado de StoreService.publish_page.
UPDATE online_store_page
SET is_published = 1,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :page_id AND hub_id = :hub_id AND is_deleted = 0;
