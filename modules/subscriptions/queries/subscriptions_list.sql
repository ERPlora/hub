-- Suscripciones del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de SubscriptionService.list_subscriptions. :status ('' = sin filtro) y
-- :customer_name ('' = sin filtro, busca por subcadena). :limit acota el resultado.
SELECT id, plan_id, customer_name, customer_email, customer_tax_id, status,
       start_date, current_period_start, current_period_end, trial_end,
       cancelled_at, cancellation_reason
FROM subscriptions_subscription
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:customer_name = '' OR customer_name LIKE '%' || :customer_name || '%')
ORDER BY created_at DESC
LIMIT :limit;
