-- Marca la pasarela como inactiva (las transacciones existentes se conservan).
-- Portado de PaymentGatewayService.deactivate_gateway.
UPDATE payment_gateways_gateway
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :gateway_id AND hub_id = :hub_id AND is_deleted = 0;
