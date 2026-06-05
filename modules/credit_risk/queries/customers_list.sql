-- Perfiles de crédito del hub (con filtro opcional por estado). Runtime inyecta :hub_id.
-- Portado de CreditRiskService.list_customers. available_credit = credit_limit - current_exposure
-- (sin flooring aquí; el UI/WASM lo presenta como máx(0, ...)). :status '' = sin filtro.
SELECT id, customer_ref, customer_name, credit_limit, payment_terms_days,
       current_exposure, (credit_limit - current_exposure) AS available_credit,
       credit_score, score_calculated_at, status, notes, created_at
FROM credit_risk_customer
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY customer_name ASC;
