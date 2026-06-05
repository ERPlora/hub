-- Despublica (oculta) una ficha de producto. Runtime inyecta :current_user_id, :now.
-- Portado de StoreService.unpublish_product.
UPDATE online_store_product
SET is_published = 0,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
