-- Marca un apunte como NO conciliado (idempotente). Runtime inyecta :current_user_id, :now.
-- Portado de BankingService.unreconcile_transaction. No mueve dinero: solo el flag + limpia
-- reconciled_at. El WHERE is_reconciled = 1 hace el no-op idempotente si ya estaba sin conciliar.
UPDATE banking_transaction
SET is_reconciled = 0,
    reconciled_at = NULL,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :transaction_id AND hub_id = :hub_id AND is_deleted = 0 AND is_reconciled = 1;
