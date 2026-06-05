-- e-Facturas del hub con filtro opcional por estado. Runtime inyecta :hub_id.
-- Portado de RoFiscalService.list_efacturas. :status = '' => sin filtro.
SELECT id, document_number, invoice_ref, document_type, supplier_cif, customer_cif,
       total_amount, vat_amount, status, upload_id, submission_date,
       error_code, created_at
FROM fiscal_romania_efactura
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
