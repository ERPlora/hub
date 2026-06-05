-- Cancelar pedido: draft|confirmed -> cancelled. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de PurchaseOrderService.cancel_order. Si se aporta :reason se anexa a las notas.
-- Guarda de estado (solo draft|confirmed) en el WHERE.
UPDATE purchase_orders_order SET
    status = 'cancelled',
    notes = CASE
              WHEN :reason = '' THEN notes
              ELSE TRIM(notes || char(10) || '[CANCELLED] ' || :reason)
            END,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id
  AND hub_id = :hub_id
  AND is_deleted = 0
  AND status IN ('draft', 'confirmed');
