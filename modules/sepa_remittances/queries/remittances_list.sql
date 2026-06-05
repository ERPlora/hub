-- Listado de remesas con filtros opcionales por estado y tipo. Runtime inyecta :hub_id.
-- Portado de SepaService.list_remittances (:status / :remittance_type = '' → sin filtro).
SELECT id, remittance_id, remittance_type, execution_date, total_amount,
       total_count, currency, status, generated_at, sent_at, notes, created_at
FROM sepa_remittances_remittance
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:remittance_type = '' OR remittance_type = :remittance_type)
ORDER BY created_at DESC
LIMIT :limit;
