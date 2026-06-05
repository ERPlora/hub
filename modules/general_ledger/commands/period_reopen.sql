-- Reapertura de periodo: closed → open (para correcciones). Runtime inyecta
-- :hub_id, :current_user_id, :now. Portado de GeneralLedgerService.reopen_period.
-- La guarda "ya abierto" la cubre el WHERE (status='closed').
UPDATE general_ledger_period
SET status     = 'open',
    closed_at  = NULL,
    closed_by_ref = '',
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :period_id AND status = 'closed';
