INSERT INTO inventory_product (id, hub_id, name, sku, price, stock, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES (:new_id, :hub_id, :name, :sku, :price, :stock, 0, :current_user_id, :current_user_id, :now, :now);
