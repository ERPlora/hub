-- Desactivar (soft-disable) una regla de descuento. Portado de PricingService.deactivate_rule.
-- No es soft-delete: la fila sigue viva (is_deleted=0), solo deja de estar activa.
UPDATE pricing_discount_rule
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :rule_id AND hub_id = :hub_id AND is_deleted = 0;
