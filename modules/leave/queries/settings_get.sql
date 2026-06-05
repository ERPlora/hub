-- Ajustes de ausencias del hub (singleton). Runtime inyecta :hub_id.
SELECT id, default_days_per_year, require_approval, min_advance_days,
       allow_half_days, max_consecutive_days
FROM leave_settings
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
