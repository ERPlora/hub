-- Declaraciones JPK del hub con filtro opcional por tipo. Runtime inyecta :hub_id.
-- Portado de RoFiscalService.list_jpks. :declaration_type = '' => sin filtro.
SELECT id, declaration_type, period_start, period_end, status, total_amount,
       submitted_at, created_at
FROM fiscal_romania_jpk
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:declaration_type = '' OR declaration_type = :declaration_type)
ORDER BY created_at DESC;
