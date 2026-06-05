-- Lista de conciliaciones (matches) del hub, con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de routes.list_matches. Filtros: :match_type ('' = todos), :statement_id ('' = todos)
-- y :statement_line_id ('' = todos). El filtro por extracto cruza con la tabla de líneas
-- PROPIA del módulo (bank_reconciliation_line), nunca con tablas de otro módulo.
SELECT m.id, m.statement_line_id, m.ledger_entry_ref, m.amount_matched,
       m.match_type, m.confidence_score, m.matched_by_ref, m.notes, m.created_at
FROM bank_reconciliation_match m
JOIN bank_reconciliation_line l ON l.id = m.statement_line_id AND l.is_deleted = 0
WHERE m.hub_id = :hub_id AND m.is_deleted = 0
  AND (:match_type = '' OR m.match_type = :match_type)
  AND (:statement_id = '' OR l.statement_id = :statement_id)
  AND (:statement_line_id = '' OR m.statement_line_id = :statement_line_id)
ORDER BY m.created_at DESC;
