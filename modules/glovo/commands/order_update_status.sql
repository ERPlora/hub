-- Transición de estado de un pedido Glovo. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de GlovoService.update_order_status. El enum new_status lo valida el JSON Schema.
UPDATE glovo_order
SET status     = :new_status,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
