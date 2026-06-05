-- Ciclos de facturación de una suscripción (scope hub_id). Runtime inyecta :hub_id.
-- Portado del bloque de cycles en SubscriptionService.get_subscription (orden por period_start).
SELECT id, subscription_id, period_start, period_end, amount, status, invoiced_at
FROM subscriptions_billing_cycle
WHERE subscription_id = :subscription_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY period_start ASC;
