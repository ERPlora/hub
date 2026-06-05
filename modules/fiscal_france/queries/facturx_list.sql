-- Documentos Factur-X del hub con filtro opcional por estado. Runtime inyecta :hub_id.
-- Portado de FrFiscalService.list_facturx. (:status = '' → sin filtro.)
SELECT id, document_number, invoice_ref, supplier_siret, customer_siret,
       total_amount_ht, vat_amount, total_amount_ttc, status,
       submission_date, created_at
FROM fiscal_france_facturx
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
