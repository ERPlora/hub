-- Edición de widget. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DashboardService.update_widget. La validación de widget_type (enum) = JSON Schema.
UPDATE dashboards_widget
SET widget_type = :widget_type,
    title = :title,
    position_x = :position_x,
    position_y = :position_y,
    width = :width,
    height = :height,
    config = :config,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :widget_id;
