-- Alta de widget en un panel. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de DashboardService.add_widget. La validación de widget_type (enum) la hace el
-- JSON Schema; la existencia del panel la valida el runtime/SDK antes de insertar.
INSERT INTO dashboards_widget
  (id, hub_id, dashboard_id, widget_type, title,
   position_x, position_y, width, height, config,
   data_cache, cached_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :dashboard_id, :widget_type, :title,
   :position_x, :position_y, :width, :height, :config,
   NULL, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
