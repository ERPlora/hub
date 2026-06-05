-- Widgets de un panel, ordenados por posición en la rejilla. Runtime inyecta :hub_id.
-- Portado de DashboardService.get_dashboard (sección widgets).
SELECT id, dashboard_id, widget_type, title, position_x, position_y,
       width, height, config, data_cache, cached_at
FROM dashboards_widget
WHERE hub_id = :hub_id AND is_deleted = 0 AND dashboard_id = :dashboard_id
ORDER BY position_y ASC, position_x ASC;
