-- Soft-delete de categoría de servicios. Portado de CategoryService.delete_category.
-- El legacy bloquea si tiene servicios asignados; ese chequeo se hace en el SDK/handler
-- antes de invocar (ver WASM-TODO.md). Aquí aplicamos el soft-delete.
UPDATE services_category
SET is_active = 0, is_deleted = 1, deleted_at = :now,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :category_id AND hub_id = :hub_id;
