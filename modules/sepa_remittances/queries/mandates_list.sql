-- Listado de mandatos SEPA con filtro opcional por estado. Runtime inyecta :hub_id.
-- Portado de SepaService.list_mandates (default status='active'; :status = '' → sin filtro).
SELECT id, mandate_id, debtor_name, debtor_iban, debtor_bic, creditor_id,
       signed_date, status, revoked_at, scheme, notes, created_at
FROM sepa_remittances_mandate
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
