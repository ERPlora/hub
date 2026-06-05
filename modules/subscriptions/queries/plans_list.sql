-- Planes de suscripción del hub. Runtime inyecta :hub_id.
-- Portado de SubscriptionService.list_plans. :active_only ('1' = solo activos, '' = todos).
SELECT id, code, name, description, billing_period, price, trial_days, is_active, features
FROM subscriptions_plan
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY code ASC;
