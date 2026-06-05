-- Alta de pasarela. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PaymentGatewayService.create_gateway. La validación de provider permitido y la unicidad
-- de `code` por hub las cubre el JSON Schema + el índice único uq_payment_gateway_hub_code.
-- :config y :supported_currencies llegan como texto JSON.
INSERT INTO payment_gateways_gateway
  (id, hub_id, code, name, provider, is_active, is_test_mode, config,
   supports_refunds, supported_currencies,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :provider, 1, :is_test_mode, :config,
   :supports_refunds, :supported_currencies,
   0, :current_user_id, :current_user_id, :now, :now);
