-- Categorías de coste del hub. Runtime inyecta :hub_id.
-- Portado de ProjectCostingService.list_categories (active_only por defecto, orden por code).
-- El bind :active_only (1 = solo activas, 0 = todas) lo controla el SDK/UI.
SELECT id, code, name, parent_id, is_active
FROM project_costing_category
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
