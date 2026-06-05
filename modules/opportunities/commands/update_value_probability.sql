-- Actualizar value y/o probability de una oportunidad abierta.
-- Portado de OpportunityService.update_value_probability. Guarda: solo si está abierta.
-- Partial update: el handler/runtime pasa los valores actuales como :value/:probability cuando
-- el cliente omite uno (el SDK rellena con el valor vigente). Rangos (value>=0, 0<=prob<=100)
-- los garantiza el schema. weighted_value se recalcula en lectura/UI.
UPDATE opportunities_opportunity
SET value       = :value,
    probability = :probability,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :opportunity_id AND hub_id = :hub_id AND is_deleted = 0
  AND stage NOT IN ('won', 'lost');
