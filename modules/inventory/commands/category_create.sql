-- Alta de categoría. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CategoryService.create_category (slug auto si vacío → lo calcula el SDK/handler).
INSERT INTO inventory_category
  (id, hub_id, name, slug, icon, color, description, "order", is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :slug, :icon, :color, :description, :order, 1,
   0, :current_user_id, :current_user_id, :now, :now);
