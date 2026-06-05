-- Comparticiones activas de un panel. Runtime inyecta :hub_id.
-- Portado de DashboardService.list_shares.
SELECT id, dashboard_id, shared_with_ref, access_level, shared_at, shared_by_ref
FROM dashboards_share
WHERE hub_id = :hub_id AND is_deleted = 0 AND dashboard_id = :dashboard_id
ORDER BY shared_at ASC;
