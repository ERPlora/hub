-- Alta de conexión Stripe. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de StripeService.create_connection. La unicidad (hub, account_id) la garantiza
-- el índice uq_stripe_conn_hub_acct; la comprobación previa de duplicado y el hash del
-- webhook secret (nunca el valor crudo) van a runtime — ver WASM-TODO.
INSERT INTO stripe_connection
  (id, hub_id, name, account_id, publishable_key, webhook_secret_hash,
   is_active, is_test_mode, capabilities, country, default_currency,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :account_id, :publishable_key, '',
   1, :is_test_mode, '[]', :country, :default_currency,
   0, :current_user_id, :current_user_id, :now, :now);
