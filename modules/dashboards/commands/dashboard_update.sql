-- Edición de panel. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DashboardService.update_dashboard. Solo afecta a la fila del hub no borrada.
-- La unicidad de code al renombrar la garantiza el índice ix_dash_hub_code.
UPDATE dashboards_dashboard
SET code = :code,
    name = :name,
    description = :description,
    layout = :layout,
    is_default = :is_default,
    is_public = :is_public,
    owner_ref = :owner_ref,
    theme = :theme,
    refresh_interval_sec = :refresh_interval_sec,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :dashboard_id;
