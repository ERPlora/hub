-- Mover una oportunidad a otra etapa (no won/lost). Portado de OpportunityService.update_stage.
-- Guarda: solo si NO está cerrada (stage NOT IN ('won','lost')). La validación de que new_stage
-- es válido y no es won/lost la hace el schema/runtime. El bump de probability al default de la
-- etapa (solo si la actual es menor) NO cabe en una sola sentencia → ver WASM-TODO; aquí solo
-- movemos la etapa de forma idempotente y segura.
UPDATE opportunities_opportunity
SET stage      = :new_stage,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :opportunity_id AND hub_id = :hub_id AND is_deleted = 0
  AND stage NOT IN ('won', 'lost');
