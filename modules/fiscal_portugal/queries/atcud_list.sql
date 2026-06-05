-- Documentos ATCUD del hub (filtro opcional por tipo de documento). Runtime inyecta :hub_id.
-- Portado de PtFiscalService.list_atcud. (:document_type = '' => sin filtro.)
SELECT id, document_type, document_series_code, document_number, atcud,
       invoice_ref, hash_value, hash_method, signed, created_at
FROM fiscal_portugal_atcud
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:document_type = '' OR document_type = :document_type)
ORDER BY created_at DESC;
