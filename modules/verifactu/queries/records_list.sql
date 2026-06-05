-- Registros VeriFactu (más recientes primero) con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de VerifactuService.list_records + routes.records_list.
-- Binds opcionales: :status y :record_type ('' = sin filtro); :search ('' = sin filtro).
SELECT id, sequence_number, invoice_number, invoice_date,
       record_type, invoice_type, issuer_nif, issuer_name,
       base_amount, tax_amount, total_amount,
       status, transmission_timestamp, retry_count, aeat_csv,
       generation_timestamp
FROM verifactu_record
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:record_type = '' OR record_type = :record_type)
  AND (:search = ''
       OR invoice_number LIKE '%' || :search || '%'
       OR issuer_name LIKE '%' || :search || '%'
       OR issuer_nif LIKE '%' || :search || '%')
ORDER BY sequence_number DESC
LIMIT :limit;
