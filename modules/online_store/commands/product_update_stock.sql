-- Fija el stock disponible de una ficha de producto. Runtime inyecta :current_user_id, :now.
-- Portado de StoreService.update_stock. La validación new_stock >= 0 (entero) va a
-- WASM/runtime / JSON Schema — ver schemas/product_update_stock.json.
UPDATE online_store_product
SET stock_quantity = :new_stock,
    updated_by     = :current_user_id,
    updated_at     = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
