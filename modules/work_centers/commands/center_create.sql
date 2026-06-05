-- Alta de centro de producción. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de WorkCenterService.create_center. La validación de center_type y la guarda de
-- code duplicado por hub van a runtime/WASM (ver WASM-TODO); el índice ix_wc_hub_code
-- garantiza la unicidad de (hub_id, code) en BD.
INSERT INTO work_centers_center
  (id, hub_id, code, name, center_type, capacity_per_hour, hourly_cost,
   location_ref, is_active, calendar, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :center_type, :capacity_per_hour, :hourly_cost,
   :location_ref, 1, :calendar, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
