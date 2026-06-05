-- Documentos FatturaPA del hub con filtro opcional por estado.
-- Portado de ItFiscalService.list_fatturapa. Runtime inyecta :hub_id.
-- (:status debe pasarse: '' = sin filtro.)
SELECT id, document_number, invoice_ref, supplier_piva, customer_piva,
       customer_codice_destinatario, total_imponibile, total_iva, total_documento,
       status, sdi_id, submission_date, rejection_reason, created_at
FROM fiscal_italy_fatturapa
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
