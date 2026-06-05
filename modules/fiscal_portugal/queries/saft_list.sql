-- Exports SAF-T PT del hub (filtro opcional por estado). Runtime inyecta :hub_id.
-- Portado de PtFiscalService.list_saft. (:status = '' => sin filtro.)
-- No se devuelve xml_content (payload grande): se obtiene con saft.get si hace falta.
SELECT id, document_number, period_start, period_end, period_type,
       total_invoices, total_amount, status, generated_at, submitted_at, created_at
FROM fiscal_portugal_saft
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
