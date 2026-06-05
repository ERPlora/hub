-- Confirmar pedido: draft -> confirmed. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de PurchaseOrderService.confirm_order. La guarda de estado (solo 'draft')
-- se aplica en el WHERE: si no estaba en draft no afecta filas.
UPDATE purchase_orders_order SET
    status = 'confirmed',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id
  AND hub_id = :hub_id
  AND is_deleted = 0
  AND status = 'draft';
