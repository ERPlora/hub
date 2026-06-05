-- Un perfil de crédito por id (scope hub_id). Portado de CreditRiskService.get_customer.
-- Los eventos y alertas asociados se leen aparte (events.list / alerts.list filtrando por id).
SELECT id, customer_ref, customer_name, credit_limit, payment_terms_days,
       current_exposure, (credit_limit - current_exposure) AS available_credit,
       credit_score, score_calculated_at, status, notes, created_at
FROM credit_risk_customer
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
