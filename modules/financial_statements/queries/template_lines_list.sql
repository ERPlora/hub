-- Líneas de una plantilla, ordenadas. Runtime inyecta :hub_id. Portado del bloque de
-- line_items de FinancialReportService.get_template y del loader de los generate_*.
SELECT id, template_id, section, item_code, item_label, item_order,
       account_codes, sign, is_total
FROM financial_statements_line_item
WHERE hub_id = :hub_id AND is_deleted = 0 AND template_id = :template_id
ORDER BY item_order ASC;
