-- Una regla de comisión por id. Runtime inyecta :hub_id.
SELECT id, name, description, rule_type, rate, staff_id, service_id, category_id,
       product_id, tier_thresholds, effective_from, effective_until, priority, is_active
FROM commissions_rule
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :rule_id;
