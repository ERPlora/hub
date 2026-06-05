-- Borrado lógico (soft-delete) de un informe. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ReportService.delete_report. En legacy cascadeaba runs+subscriptions; aquí el
-- borrado en cascada de filas hijas (runs/subscriptions) lo orquesta el runtime — ver WASM-TODO.
UPDATE reports_report
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :report_id AND hub_id = :hub_id AND is_deleted = 0;
