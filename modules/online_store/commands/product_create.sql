-- Alta de ficha de producto en el escaparate. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de StoreService.create_product. La validación del slug único por hub la garantiza
-- el índice ix_online_store_product_hub_slug; el parseo/validación del precio (Decimal) va a
-- WASM/runtime — ver WASM-TODO. Se crea sin publicar (is_published = 0).
INSERT INTO online_store_product
  (id, hub_id, product_ref, slug, name, description, short_description,
   price, sale_price, stock_quantity, sku, images, is_published,
   seo_title, seo_description, weight, dimensions,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :product_ref, :slug, :name, :description, '',
   :price, NULL, :stock_quantity, '', '[]', 0,
   '', '', NULL, '',
   0, :current_user_id, :current_user_id, :now, :now);
