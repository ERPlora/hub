-- Alta de item (precio por producto/bracket) en una lista. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de PricingService.add_price_item.
INSERT INTO pricing_price_list_item
  (id, hub_id, price_list_id, product_ref, price, min_quantity, max_quantity,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :price_list_id, :product_ref, :price, :min_quantity, :max_quantity,
   0, :current_user_id, :current_user_id, :now, :now);
