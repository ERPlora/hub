-- Aprobación de una transacción de comisión pendiente. Runtime inyecta :hub_id, :now,
-- :current_user_id. Portado de CommissionsService.approve_transaction.
-- La transición solo es válida desde status='pending' (de ahí el WHERE status='pending');
-- si la fila no está pendiente, no se actualiza ninguna fila (rowcount=0 → el runtime
-- puede traducirlo a error de transición de estado).
UPDATE commissions_transaction
SET status         = 'approved',
    approved_at    = :now,
    approved_by_id = :current_user_id,
    updated_by     = :current_user_id,
    updated_at     = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :transaction_id AND status = 'pending';
