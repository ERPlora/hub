-- Comunicações à AT del hub (filtro opcional por estado). Runtime inyecta :hub_id.
-- Portado de PtFiscalService.list_at_communications. (:status = '' => sin filtro.)
-- No se devuelve content_xml (payload grande).
SELECT id, document_number, communication_type, reference_period,
       submission_id, status, submitted_at, created_at
FROM fiscal_portugal_at_comm
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
