-- Lista de definiciones de KPI del hub. Runtime inyecta :hub_id.
-- Portado de KPIService.list_kpis. Filtros opcionales: :category ('' = sin filtro),
-- :is_active (1 = solo activos, 0 = solo inactivos; el SDK decide).
SELECT id, code, name, description, unit, kpi_type, aggregation, category,
       target_value, target_direction, critical_threshold, warning_threshold,
       is_active, owner_ref, created_at
FROM kpis_kpi
WHERE hub_id = :hub_id AND is_deleted = 0
  AND is_active = :is_active
  AND (:category = '' OR category = :category)
ORDER BY code ASC;
