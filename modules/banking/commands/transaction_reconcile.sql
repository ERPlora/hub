-- Marca un apunte como conciliado (idempotente). Runtime inyecta :current_user_id, :now.
-- Portado de BankingService.reconcile_transaction. No mueve dinero: solo el flag + sello.
-- El WHERE is_reconciled = 0 hace el no-op idempotente si ya estaba conciliado.
UPDATE banking_transaction
SET is_reconciled = 1,
    reconciled_at = :now,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :transaction_id AND hub_id = :hub_id AND is_deleted = 0 AND is_reconciled = 0;
