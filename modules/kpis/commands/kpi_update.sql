-- Actualización de campos mutables de un KPI (code es inmutable). Runtime inyecta
-- :hub_id, :current_user_id, :now. Portado de KPIService.update_kpi.
-- A diferencia del legacy (subset dinámico de campos), aquí se actualiza el conjunto
-- completo de campos mutables: el SDK debe enviar TODOS los valores (los actuales para
-- los que no cambian). La validación de enums la cubre el schema.
UPDATE kpis_kpi
SET name               = :name,
    description        = :description,
    unit               = :unit,
    kpi_type           = :kpi_type,
    aggregation        = :aggregation,
    category           = :category,
    target_value       = :target_value,
    target_direction   = :target_direction,
    critical_threshold = :critical_threshold,
    warning_threshold  = :warning_threshold,
    owner_ref          = :owner_ref,
    is_active          = :is_active,
    updated_by         = :current_user_id,
    updated_at         = :now
WHERE id = :kpi_id AND hub_id = :hub_id AND is_deleted = 0;
