-- Histórico de valores de un KPI (más recientes primero). Runtime inyecta :hub_id.
-- Portado del bloque include_history de KPIService.get_kpi. El límite lo aplica el SDK/UI.
SELECT id, kpi_id, period_start, period_end, value, target_at_time,
       computed_at, recorded_by_ref, notes
FROM kpis_value
WHERE hub_id = :hub_id AND is_deleted = 0 AND kpi_id = :kpi_id
ORDER BY period_start DESC;
