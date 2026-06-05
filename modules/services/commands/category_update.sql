-- Edición de categoría de servicios. Portado de CategoryService.update_category.
UPDATE services_category SET
  name        = :name,
  slug        = :slug,
  description = :description,
  icon        = :icon,
  color       = :color,
  sort_order  = :sort_order,
  is_active   = :is_active,
  updated_by  = :current_user_id,
  updated_at  = :now
WHERE id = :category_id AND hub_id = :hub_id AND is_deleted = 0;
