-- Alta de definición de informe. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ReportService.create_report. La validación de report_type (enum) y el chequeo de
-- unicidad de code la cubre el schema + el índice uq_reports_hub_code.
-- Los campos JSON (filters/columns/groupings/sorts/schedule) llegan ya serializados como TEXT.
INSERT INTO reports_report
  (id, hub_id, code, name, description, report_type, data_source,
   filters, columns, groupings, sorts, is_public, schedule, owner_ref,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :report_type, :data_source,
   :filters, :columns, :groupings, :sorts, :is_public, :schedule, :owner_ref,
   0, :current_user_id, :current_user_id, :now, :now);
