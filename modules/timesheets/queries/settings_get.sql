-- Configuración (singleton) de timesheets del hub. Runtime inyecta :hub_id.
-- Portado de TimesheetService.get_settings. Si no existe fila, el SDK/UI aplica
-- los defaults (default_billable=1, require_approval=1, approval_period='weekly').
SELECT id, default_billable, require_approval, approval_period
FROM timesheets_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
