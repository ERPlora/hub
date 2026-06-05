-- Devoluciones de un cargo concreto (FK interna). Runtime inyecta :hub_id.
-- Portado de la rama include_refunds de StripeService.get_charge.
SELECT id, charge_id, refund_id, amount, status, reason,
       created_at_stripe, created_at
FROM stripe_refund
WHERE charge_id = :charge_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC;
