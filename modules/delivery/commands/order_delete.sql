-- Borrado lógico (soft-delete) de un pedido. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DeliveryService.delete_order. No borra físicamente: marca is_deleted=1.
UPDATE delivery_order
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
