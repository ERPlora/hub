-- Un documento FatturaPA por id (scope hub_id), incluyendo el XML generado.
-- Runtime inyecta :hub_id.
SELECT id, document_number, invoice_ref, supplier_piva, customer_piva,
       customer_codice_destinatario, total_imponibile, total_iva, total_documento,
       status, xml_content, sdi_id, submission_date, rejection_reason, created_at
FROM fiscal_italy_fatturapa
WHERE id = :fatturapa_id AND hub_id = :hub_id AND is_deleted = 0;
