-- Soft-delete de ficha de producto (contrato de fila §2.5). Runtime inyecta :current_user_id, :now.
-- (No existe en el legacy; en hub-next preferimos soft-delete + audit a borrado duro.)
UPDATE online_store_product
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0;
