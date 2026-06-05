-- Categorías de auditoría del hub (orden por code). Portado de AuditService.list_categories.
-- Runtime inyecta :hub_id.
SELECT id, code, name, severity_default, retention_days
FROM audit_log_category
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY code ASC;
