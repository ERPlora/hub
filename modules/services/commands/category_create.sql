-- Alta de categoría de servicios. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CategoryService.create_category (slug auto-calculado por el SDK/handler).
INSERT INTO services_category
  (id, hub_id, name, slug, description, parent_id, icon, color, sort_order, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :slug, :description, :parent_id, :icon, :color, :sort_order, 1,
   0, :current_user_id, :current_user_id, :now, :now);
