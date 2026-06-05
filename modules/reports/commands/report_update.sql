-- Actualización de definición de informe. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ReportService.update_report. Solo campos actualizables; los JSON llegan ya
-- serializados como TEXT. Pasar el valor actual cuando no se quiera cambiar un campo.
UPDATE reports_report
SET name        = :name,
    description = :description,
    report_type = :report_type,
    data_source = :data_source,
    filters     = :filters,
    columns     = :columns,
    groupings   = :groupings,
    sorts       = :sorts,
    is_public   = :is_public,
    schedule    = :schedule,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :report_id AND hub_id = :hub_id AND is_deleted = 0;
