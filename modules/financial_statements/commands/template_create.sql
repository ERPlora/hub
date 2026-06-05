-- Alta de plantilla de informe. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de FinancialReportService.create_template. La validación de report_type (enum) la
-- hace el schema; la unicidad de code por hub la garantiza ix_fs_template_hub_code.
INSERT INTO financial_statements_template
  (id, hub_id, code, name, report_type, structure, is_default, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :report_type, :structure, :is_default, 1,
   0, :current_user_id, :current_user_id, :now, :now);
