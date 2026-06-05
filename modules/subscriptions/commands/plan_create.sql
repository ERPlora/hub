-- Alta de plan de suscripción. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de SubscriptionService.create_plan. La validación de billing_period (enum),
-- price >= 0 y trial_days >= 0 la hace el JSON Schema; (hub, code) único lo garantiza el
-- índice uq_subscriptions_plan_hub_code. features llega serializado como JSON string ('{}' por defecto).
INSERT INTO subscriptions_plan
  (id, hub_id, code, name, description, billing_period, price, trial_days, features,
   is_active, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :billing_period, :price, :trial_days, :features,
   1, 0, :current_user_id, :current_user_id, :now, :now);
