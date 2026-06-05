-- Plantillas de turno activas del hub, filtro opcional por sede.
-- Runtime inyecta :hub_id. Portado de ShiftTemplateService.list_shift_templates.
-- duration_hours (descontando break, con wrap nocturno) lo calcula el SDK/WASM, no el SQL.
SELECT id, name, location_id, start_time, end_time, break_minutes,
       color, is_active, min_staff, max_staff, role_required, required_skills
FROM workforce_planning_shift_template
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
  AND (:location_id = '' OR location_id = :location_id)
ORDER BY start_time ASC;
