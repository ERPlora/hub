-- Lista de documentos ZUGFeRD del hub, con filtro opcional por profile.
-- Runtime inyecta :hub_id. :profile vacío ('') = todos. Portado de DeFiscalService.list_zugferd.
SELECT id, document_number, invoice_ref, supplier_ust_id, customer_name,
       total_netto, total_brutto, profile, pdf_a3_path, created_at
FROM fiscal_germany_zugferd
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:profile = '' OR profile = :profile)
ORDER BY created_at DESC
LIMIT :limit;
