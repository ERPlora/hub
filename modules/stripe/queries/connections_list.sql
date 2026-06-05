-- Conexiones Stripe del hub (con filtro opcional por activas). Runtime inyecta :hub_id.
-- Portado de StripeService.list_connections. (:active_only = 1 → solo activas; 0 → todas.)
SELECT id, name, account_id, publishable_key, is_active, is_test_mode,
       capabilities, country, default_currency, created_at
FROM stripe_connection
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY created_at DESC;
