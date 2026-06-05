-- Cierre de periodo: open → closed. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de GeneralLedgerService.close_period. La guarda "ya cerrado" la cubre el WHERE
-- (status='open'); si afecta 0 filas el runtime/SDK devuelve error already_closed/not_found.
UPDATE general_ledger_period
SET status     = 'closed',
    closed_at  = :now,
    closed_by_ref = :current_user_id,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :period_id AND status = 'open';
