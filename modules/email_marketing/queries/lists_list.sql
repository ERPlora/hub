-- Listas de destinatarios del hub. Runtime inyecta :hub_id.
-- Portado de EmailMarketingService.list_lists. El filtro active_only lo aplica el bind:
-- :active_only = 1 → solo activas; 0 → todas.
SELECT id, name, description, is_active, total_subscribers, created_at
FROM email_marketing_list
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY name ASC;
