-- Alta de zona. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TableService.create_zone.
INSERT INTO tables_zone
  (id, hub_id, name, description, color, sort_order, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :color, :sort_order, 1,
   0, :current_user_id, :current_user_id, :now, :now);
