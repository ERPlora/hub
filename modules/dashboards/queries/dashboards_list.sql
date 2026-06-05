-- Lista de paneles del hub (filtro opcional por is_public/owner_ref). Runtime inyecta :hub_id.
-- Portado de DashboardService.list_dashboards. Filtros opcionales: ''/-1 = sin filtro.
-- (:is_public: -1 = sin filtro, 0 = privados, 1 = públicos; :owner_ref: '' = sin filtro.)
SELECT id, code, name, description, layout, is_default, is_public,
       owner_ref, theme, refresh_interval_sec, created_at
FROM dashboards_dashboard
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:is_public = -1 OR is_public = :is_public)
  AND (:owner_ref = '' OR owner_ref = :owner_ref)
ORDER BY name ASC;
