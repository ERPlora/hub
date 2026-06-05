-- Marca un ciclo de facturación como pagado y estampa invoiced_at si aún no lo tenía.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de SubscriptionService.mark_cycle_paid.
-- COALESCE preserva un invoiced_at previo; si era NULL se fija a la fecha de :now (YYYY-MM-DD).
-- La guarda "ya pagado" (already_paid) la cubre el WHERE status <> 'paid'.
UPDATE subscriptions_billing_cycle
SET status = 'paid',
    invoiced_at = COALESCE(invoiced_at, substr(:now, 1, 10)),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :cycle_id AND hub_id = :hub_id AND is_deleted = 0 AND status <> 'paid';
