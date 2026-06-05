-- Alta de centro de trabajo. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TimeControlService.create_workplace.
INSERT INTO time_control_workplace
  (id, hub_id, name, address, latitude, longitude, radius_meters,
   is_active, is_default, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :address, :latitude, :longitude, :radius_meters,
   1, :is_default, 0, :current_user_id, :current_user_id, :now, :now);
