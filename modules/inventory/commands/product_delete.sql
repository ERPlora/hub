-- Soft-delete de producto (coherente con el contrato de fila §2.5).
-- (El legacy hace delete duro; en hub-next preferimos soft-delete + audit.)
UPDATE inventory_product
SET is_deleted = 1, deleted_at = :now, is_active = 0,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id;
