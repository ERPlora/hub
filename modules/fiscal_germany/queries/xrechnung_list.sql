-- Lista de documentos XRechnung del hub, con filtro opcional por status.
-- Runtime inyecta :hub_id. :status vacío ('') = todos. Portado de DeFiscalService.list_xrechnung.
SELECT id, document_number, invoice_ref, supplier_ust_id, customer_leitweg_id,
       total_netto, total_steuer, total_brutto, status, submission_date, created_at
FROM fiscal_germany_xrechnung
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
