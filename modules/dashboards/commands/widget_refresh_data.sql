-- Actualiza el payload cacheado de un widget (data_cache + cached_at).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de DashboardService.refresh_widget_data.
-- :data es JSON libre con el payload calculado por el cliente/host.
UPDATE dashboards_widget
SET data_cache = :data,
    cached_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :widget_id;
