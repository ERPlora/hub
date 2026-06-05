-- Reembolsos de una transacción (scope hub_id), más recientes primero.
-- Portado de la sub-consulta de PaymentGatewayService.get_transaction (include_refunds).
SELECT id, transaction_id, amount_refunded, reason, status,
       refund_provider_id, refunded_at, created_at
FROM payment_gateways_refund
WHERE transaction_id = :transaction_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC;
