-- Edición de producto (campos editables; la UI envía el conjunto completo, Tier 0/1).
-- Portado de ProductService.update_product (name/price/cost/low_stock_threshold/is_active).
UPDATE inventory_product SET
  name = :name,
  price = :price,
  cost = :cost,
  low_stock_threshold = :low_stock_threshold,
  is_active = :is_active,
  updated_by = :current_user_id,
  updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
