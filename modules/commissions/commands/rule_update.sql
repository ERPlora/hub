-- Edición de regla de comisión. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de CommissionsService.update_rule. Patrón COALESCE-vacío: cada campo de texto
-- se actualiza solo si el bind no es '' (NULL); priority/is_active aceptan -1 como "no tocar".
UPDATE commissions_rule
SET name            = COALESCE(NULLIF(:name, ''), name),
    description     = COALESCE(:description, description),
    rule_type       = COALESCE(NULLIF(:rule_type, ''), rule_type),
    rate            = COALESCE(:rate, rate),
    tier_thresholds = COALESCE(NULLIF(:tier_thresholds, ''), tier_thresholds),
    effective_from  = COALESCE(:effective_from, effective_from),
    effective_until = COALESCE(:effective_until, effective_until),
    priority        = CASE WHEN :priority < 0 THEN priority ELSE :priority END,
    is_active       = CASE WHEN :is_active < 0 THEN is_active ELSE :is_active END,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :rule_id;
