-- Ajuste de stock por :delta (puede ser negativo). Por defecto no baja de 0
-- (MAX(0, stock+delta)); el legacy permite negativo solo con allow_negative.
-- Portado de ProductService.adjust_stock. Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE inventory_product
SET stock = MAX(0, stock + :delta),
    updated_by = :current_user_id, updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
