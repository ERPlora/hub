-- Reglas de descuento activas del hub, ordenadas por prioridad (ascendente = mayor precedencia).
-- Portado de PricingService.list_discount_rules (active_only por defecto, orden priority, code).
SELECT id, code, name, rule_type, value, min_amount, max_amount, applies_to,
       conditions, valid_from, valid_until, is_active, priority
FROM pricing_discount_rule
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY priority ASC, code ASC;
