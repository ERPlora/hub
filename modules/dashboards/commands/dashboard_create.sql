-- Alta de panel. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de DashboardService.create_dashboard. La unicidad de (hub, code) la garantiza
-- el índice ix_dash_hub_code. is_default se fuerza a 0 en el alta (igual que el legacy).
INSERT INTO dashboards_dashboard
  (id, hub_id, code, name, description, layout, is_default, is_public,
   owner_ref, theme, refresh_interval_sec,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :layout, 0, :is_public,
   :owner_ref, :theme, :refresh_interval_sec,
   0, :current_user_id, :current_user_id, :now, :now);
