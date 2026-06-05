-- Lista de transacciones del hub (más recientes primero). Runtime inyecta :hub_id.
-- Portado de PaymentGatewayService.list_transactions. Filtros opcionales por gateway/status/email
-- se aplican vía COALESCE (binds vacíos = sin filtro) para mantener Tier 0 declarativo.
SELECT id, gateway_id, transaction_id, reference, amount, currency, status,
       customer_email, payment_method_type, error_code, captured_at, created_at
FROM payment_gateways_transaction
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:gateway_id = '' OR gateway_id = :gateway_id)
  AND (:status = ''     OR status = :status)
  AND (:customer_email = '' OR customer_email LIKE '%' || :customer_email || '%')
ORDER BY created_at DESC
LIMIT 100;
