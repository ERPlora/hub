-- Un cargo concreto del hub. Runtime inyecta :hub_id.
-- Portado de StripeService.get_charge (el historial de refunds se obtiene aparte con refunds_by_charge).
SELECT id, connection_id, charge_id, payment_intent_id, amount, currency,
       status, customer_email, payment_method, description,
       created_at_stripe, created_at
FROM stripe_charge
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
