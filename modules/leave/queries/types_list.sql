-- Tipos de ausencia activos del hub. Runtime inyecta :hub_id.
-- Portado de LeaveService.list_types (solo activos, ordenados por nombre).
SELECT id, name, days_per_year, is_paid, color, is_active
FROM leave_type
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY name ASC;
