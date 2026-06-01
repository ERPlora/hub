-- Soft-delete de categoría. El legacy bloquea si hay productos activos vinculados;
-- ese chequeo se hace en el SDK/handler antes de invocar (o por evento), aquí
-- aplicamos el soft-delete. Portado de CategoryService.delete_category.
UPDATE inventory_category
SET is_active = 0, is_deleted = 1, deleted_at = :now,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :category_id AND hub_id = :hub_id;
