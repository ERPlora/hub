-- Una definición de KPI por id. Runtime inyecta :hub_id.
-- Portado de KPIService.get_kpi (cabecera; el histórico se obtiene con kpis.values.list).
SELECT id, code, name, description, unit, kpi_type, aggregation, category,
       target_value, target_direction, critical_threshold, warning_threshold,
       is_active, owner_ref, created_at
FROM kpis_kpi
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :kpi_id;
