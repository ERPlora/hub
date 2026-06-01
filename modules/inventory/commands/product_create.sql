-- Alta de producto. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ProductService.create_product.
INSERT INTO inventory_product
  (id, hub_id, name, sku, ean13, description, product_type, price, cost, stock,
   low_stock_threshold, tax_class_id, image, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :sku, :ean13, :description, :product_type, :price, :cost, :stock,
   :low_stock_threshold, :tax_class_id, :image, 1,
   0, :current_user_id, :current_user_id, :now, :now);
