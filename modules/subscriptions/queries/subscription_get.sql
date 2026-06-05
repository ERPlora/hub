-- Una suscripción por id (scope hub_id). Portado de SubscriptionService.get_subscription.
-- Los ciclos asociados se piden aparte vía subscriptions.cycles.list (:subscription_id).
SELECT id, plan_id, customer_name, customer_email, customer_tax_id, status,
       start_date, current_period_start, current_period_end, trial_end,
       cancelled_at, cancellation_reason
FROM subscriptions_subscription
WHERE id = :subscription_id AND hub_id = :hub_id AND is_deleted = 0;
