-- Alta de regla de comisión. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CommissionsService.create_rule. La validación de rate>0 y de coherencia de
-- fechas (effective_from < effective_until) la garantiza el JSON Schema + runtime.
-- tier_thresholds se pasa como string JSON ('[]' por defecto).
INSERT INTO commissions_rule
  (id, hub_id, name, description, rule_type, rate, staff_id, service_id, category_id,
   product_id, tier_thresholds, effective_from, effective_until, priority, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :rule_type, :rate, :staff_id, :service_id, :category_id,
   :product_id, :tier_thresholds, :effective_from, :effective_until, :priority, 1,
   0, :current_user_id, :current_user_id, :now, :now);
