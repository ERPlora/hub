-- Requisitos de cobertura del hub, filtro opcional por sede.
-- Runtime inyecta :hub_id. El cruce con asignaciones reales (huecos de cobertura)
-- es lógica de cálculo → ver WASM-TODO (check_coverage_gaps).
SELECT id, location_id, day_of_week, shift_template_id,
       min_employees, role_required, is_active
FROM workforce_planning_coverage_requirement
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:location_id = '' OR location_id = :location_id)
ORDER BY day_of_week ASC, min_employees DESC;
