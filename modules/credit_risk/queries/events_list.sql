-- Eventos de crédito de un cliente (scope hub_id), más recientes primero.
-- Portado de CreditRiskService.get_customer (rama include_events). :customer_credit_id requerido.
SELECT id, customer_credit_id, event_type, amount, description, occurred_at, reference
FROM credit_risk_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND customer_credit_id = :customer_credit_id
ORDER BY occurred_at DESC;
