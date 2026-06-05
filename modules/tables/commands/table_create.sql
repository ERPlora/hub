-- Alta de mesa. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TableService.create_table. Estado inicial siempre 'available'.
INSERT INTO tables_table
  (id, hub_id, zone_id, number, name, capacity, position_x, position_y,
   width, height, shape, status, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :zone_id, :number, :name, :capacity, :position_x, :position_y,
   :width, :height, :shape, 'available', 1,
   0, :current_user_id, :current_user_id, :now, :now);
