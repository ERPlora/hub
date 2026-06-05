-- Aprobación de un lote de pago pendiente. Runtime inyecta :hub_id, :now, :current_user_id.
-- Portado de CommissionsService.approve_payout. Solo válido desde status='pending'.
UPDATE commissions_payout
SET status         = 'approved',
    approved_at    = :now,
    approved_by_id = :current_user_id,
    updated_by     = :current_user_id,
    updated_at     = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :payout_id AND status = 'pending';
