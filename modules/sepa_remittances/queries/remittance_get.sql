-- Detalle de una remesa por su id de fila (UUID), incluye xml_content. Runtime inyecta :hub_id.
-- Portado de SepaService.get_remittance (las líneas se piden aparte vía sepa_remittances.lines.list).
SELECT id, remittance_id, remittance_type, execution_date, total_amount,
       total_count, currency, status, xml_content, generated_at, sent_at, notes, created_at
FROM sepa_remittances_remittance
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :remittance_id;
