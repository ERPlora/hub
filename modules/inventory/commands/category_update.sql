-- Edición de categoría. Portado de CategoryService.update_category.
UPDATE inventory_category SET
  name = :name,
  slug = :slug,
  icon = :icon,
  color = :color,
  description = :description,
  "order" = :order,
  is_active = :is_active,
  updated_by = :current_user_id,
  updated_at = :now
WHERE id = :category_id AND hub_id = :hub_id AND is_deleted = 0;
