-- Desactivación lógica de un KPI (is_active = 0; NO lo borra). Runtime inyecta
-- :hub_id, :current_user_id, :now. Portado de KPIService.deactivate_kpi.
UPDATE kpis_kpi
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :kpi_id AND hub_id = :hub_id AND is_deleted = 0;
