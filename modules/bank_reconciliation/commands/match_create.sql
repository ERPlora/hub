-- Crea una conciliación manual entre una línea y un apunte contable + marca la línea como
-- conciliada. Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Transacción: las dos
-- sentencias se ejecutan atómicamente. Portado de ReconciliationService.create_match.
-- :confidence_score lo pasa el cliente (1.000 manual, <1 auto); la derivación heurística por
-- defecto y la validación de match_type van a WASM/runtime — ver WASM-TODO.
INSERT INTO bank_reconciliation_match
  (id, hub_id, statement_line_id, ledger_entry_ref, amount_matched, match_type,
   confidence_score, matched_by_ref, notes, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :statement_line_id, :ledger_entry_ref, :amount_matched, :match_type,
   :confidence_score, :current_user_id, :notes, 0, :current_user_id, :current_user_id, :now, :now);

-- Marca la línea como conciliada.
UPDATE bank_reconciliation_line
SET is_matched = 1, matched_at = :now, updated_by = :current_user_id, updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :statement_line_id;
