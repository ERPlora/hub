-- Alta de perfil de crédito. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CreditRiskService.register_customer. La unicidad de customer_ref por hub la
-- garantiza el índice ix_credit_hub_customer_ref. Exposición y score arrancan en 0; status active.
INSERT INTO credit_risk_customer
  (id, hub_id, customer_ref, customer_name, credit_limit, payment_terms_days,
   current_exposure, credit_score, score_calculated_at, status, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :customer_ref, :customer_name, :credit_limit, :payment_terms_days,
   0, 0, NULL, 'active', '',
   0, :current_user_id, :current_user_id, :now, :now);
