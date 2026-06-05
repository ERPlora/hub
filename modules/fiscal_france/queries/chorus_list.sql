-- Facturas Chorus Pro del hub con filtro opcional por estado. Runtime inyecta :hub_id.
-- Portado de FrFiscalService.list_chorus. (:status = '' → sin filtro.)
SELECT id, document_number, invoice_ref, recipient_service_code,
       total_amount, status, upload_id, anomaly_code, created_at
FROM fiscal_france_chorus
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
