-- Borrado (soft) de panel. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DashboardService.delete_dashboard. El cascade a widgets/shares se hace en el
-- mismo command (sql multi-sentencia): se soft-borran también widgets y shares del panel.
UPDATE dashboards_dashboard
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :dashboard_id;

UPDATE dashboards_widget
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND dashboard_id = :dashboard_id;

UPDATE dashboards_share
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND dashboard_id = :dashboard_id;
