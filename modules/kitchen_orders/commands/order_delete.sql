-- Borrado lógico (soft-delete) de una comanda. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de OrderService.delete_order. La guarda (solo status pending/cancelled y sin
-- sale_id enlazado) se valida en el handler WASM antes de invocar esto.
UPDATE kitchen_orders_order
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
