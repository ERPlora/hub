-- Alta de regla de descuento. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PricingService.create_discount_rule. La validación de rule_type contra el set
-- {percent,fixed,buy_x_get_y,tiered} la fija el schema JSON; :conditions llega como texto JSON.
INSERT INTO pricing_discount_rule
  (id, hub_id, code, name, rule_type, value, min_amount, max_amount, applies_to, conditions,
   valid_from, valid_until, is_active, priority,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :rule_type, :value, :min_amount, :max_amount, :applies_to, :conditions,
   :valid_from, :valid_until, 1, :priority,
   0, :current_user_id, :current_user_id, :now, :now);
