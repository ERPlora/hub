-- Borrado (soft) de widget. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DashboardService.remove_widget.
UPDATE dashboards_widget
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :widget_id;
