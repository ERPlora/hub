-- Añade una línea a un extracto existente. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de ReconciliationService.add_statement_line.
-- La guarda "no añadir a un extracto closed" se valida en el runtime/WASM (ver WASM-TODO);
-- aquí solo se persiste la fila.
INSERT INTO bank_reconciliation_line
  (id, hub_id, statement_id, transaction_date, amount, description, counterparty,
   reference, is_matched, matched_at, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :statement_id, :transaction_date, :amount, :description, :counterparty,
   :reference, 0, NULL, 0, :current_user_id, :current_user_id, :now, :now);
