-- Una transacción por id (scope hub_id). Portado de PaymentGatewayService.get_transaction.
-- Los reembolsos asociados y el total_refunded se obtienen con refunds_for_transaction.
SELECT id, gateway_id, transaction_id, reference, amount, currency, status,
       customer_email, payment_method_type, error_code, error_message,
       raw_response, captured_at, created_at
FROM payment_gateways_transaction
WHERE id = :transaction_id AND hub_id = :hub_id AND is_deleted = 0;
