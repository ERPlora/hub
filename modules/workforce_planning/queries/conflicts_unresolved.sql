-- Conflictos de planificación sin resolver del hub.
-- Runtime inyecta :hub_id. Portado de PlanningService.get_unresolved_conflicts.
SELECT id, employee_id, employee_name, conflict_type, date,
       details, shift_assignment_id, is_resolved
FROM workforce_planning_conflict
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_resolved = 0
ORDER BY date DESC;
