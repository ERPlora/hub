-- Detalle de un mandato por su id de fila (UUID). Runtime inyecta :hub_id.
-- Portado de SepaService.get_mandate.
SELECT id, mandate_id, debtor_name, debtor_iban, debtor_bic, creditor_id,
       signed_date, status, revoked_at, scheme, notes, created_at
FROM sepa_remittances_mandate
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :mandate_id;
