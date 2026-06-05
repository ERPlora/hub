-- Upsert de la configuración singleton del módulo orders (una fila por hub_id).
-- Portado de OrderService.update_settings (get-or-create). La UI/SDK envía SIEMPRE el
-- conjunto completo de campos (los no tocados se reenvían con su valor actual).
-- Binds: :new_id, :auto_confirm, :require_customer, :default_channel,
--        :notify_on_new_order, :allow_partial_fulfillment, :current_user_id, :now
--        (+ :hub_id inyectado).
INSERT INTO orders_settings
  (id, hub_id, auto_confirm, require_customer, default_channel,
   notify_on_new_order, allow_partial_fulfillment,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :auto_confirm, :require_customer, :default_channel,
   :notify_on_new_order, :allow_partial_fulfillment,
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (hub_id) DO UPDATE SET
  auto_confirm              = :auto_confirm,
  require_customer          = :require_customer,
  default_channel           = :default_channel,
  notify_on_new_order       = :notify_on_new_order,
  allow_partial_fulfillment = :allow_partial_fulfillment,
  updated_by                = :current_user_id,
  updated_at                = :now;
