-- Detalle de un panel concreto. Runtime inyecta :hub_id.
-- Portado de DashboardService.get_dashboard (cabecera). Los widgets se piden con
-- dashboards.widgets.list. No SELECT directo a tablas de otros módulos.
SELECT id, code, name, description, layout, is_default, is_public,
       owner_ref, theme, refresh_interval_sec, created_at
FROM dashboards_dashboard
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :dashboard_id;
