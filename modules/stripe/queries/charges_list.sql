-- Cargos registrados del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de StripeService.list_charges. (:connection_id/:status/:customer_email = '' → sin filtro.)
SELECT id, connection_id, charge_id, payment_intent_id, amount, currency,
       status, customer_email, payment_method, description,
       created_at_stripe, created_at
FROM stripe_charge
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:status        = '' OR status        = :status)
  AND (:customer_email = '' OR customer_email LIKE '%' || :customer_email || '%')
ORDER BY created_at DESC
LIMIT :limit;
