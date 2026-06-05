-- Líneas de una remesa concreta. Runtime inyecta :hub_id.
-- Portado de SepaService.get_remittance (sección include_lines).
SELECT id, remittance_id, mandate_id, counterparty_name, counterparty_iban,
       amount, concept, end_to_end_id, status, rejection_reason
FROM sepa_remittances_line
WHERE hub_id = :hub_id AND is_deleted = 0 AND remittance_id = :remittance_id
ORDER BY created_at ASC;
