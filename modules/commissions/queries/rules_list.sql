-- Reglas de comisión del hub. Runtime inyecta :hub_id.
-- Portado de CommissionsService.list_rules. Por defecto solo activas (:only_active='1');
-- pasar :only_active='0' para incluir inactivas. Orden por prioridad descendente.
SELECT id, name, description, rule_type, rate, staff_id, service_id, category_id,
       product_id, tier_thresholds, effective_from, effective_until, priority, is_active
FROM commissions_rule
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:only_active = '0' OR is_active = 1)
ORDER BY priority DESC, name ASC;
