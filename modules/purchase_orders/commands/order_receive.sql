-- Recibir pedido: confirmed -> received. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de PurchaseOrderService.receive_order. Guarda de estado (solo 'confirmed') en el WHERE.
-- NOTA: el alta de stock en inventory tras recibir es lógica de integración (ver WASM-TODO.md).
UPDATE purchase_orders_order SET
    status = 'received',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id
  AND hub_id = :hub_id
  AND is_deleted = 0
  AND status = 'confirmed';
