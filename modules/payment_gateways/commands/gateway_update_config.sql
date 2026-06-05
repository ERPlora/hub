-- Reemplaza el blob JSON `config` de una pasarela. Portado de PaymentGatewayService.update_gateway_config.
-- :config llega como texto JSON.
UPDATE payment_gateways_gateway
SET config = :config,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :gateway_id AND hub_id = :hub_id AND is_deleted = 0;
