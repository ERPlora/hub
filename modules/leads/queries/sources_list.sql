-- Orígenes de lead activos del hub. Runtime inyecta :hub_id.
-- Portado de LeadService.list_sources (active_only por defecto, orden por code).
SELECT id, code, name, is_active
FROM leads_source
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY code ASC;
