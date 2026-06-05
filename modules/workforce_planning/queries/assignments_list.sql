-- Asignaciones de turno del hub en un rango de fechas, filtros opcionales por sede/empleado.
-- Runtime inyecta :hub_id. Portado de PlanningService.get_week_planning (el agrupado por
-- empleado y el cálculo de horas lo hace el SDK/WASM; aquí devolvemos las filas planas).
-- Solo estados vivos (scheduled/confirmed/completed); cancelled/no_show se excluyen aquí.
SELECT id, employee_id, employee_name, location_id, shift_template_id,
       date, start_time, end_time, break_minutes, status, notes
FROM workforce_planning_shift_assignment
WHERE hub_id = :hub_id AND is_deleted = 0
  AND status IN ('scheduled', 'confirmed', 'completed')
  AND (:date_from   = '' OR date >= :date_from)
  AND (:date_to     = '' OR date <= :date_to)
  AND (:location_id = '' OR location_id = :location_id)
  AND (:employee_id = '' OR employee_id = :employee_id)
ORDER BY date ASC, start_time ASC;
