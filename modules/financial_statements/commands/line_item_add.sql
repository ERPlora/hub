-- Alta de línea de plantilla. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de FinancialReportService.add_line_item. La validación de sign (1/-1) y de que
-- account_codes no esté vacío para líneas no-total la hace el schema/runtime.
INSERT INTO financial_statements_line_item
  (id, hub_id, template_id, section, item_code, item_label, item_order,
   account_codes, sign, is_total,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :template_id, :section, :item_code, :item_label, :item_order,
   :account_codes, :sign, :is_total,
   0, :current_user_id, :current_user_id, :now, :now);
