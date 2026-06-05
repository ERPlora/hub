-- Actualización de campos mutables de un agente. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de AgentService.update_agent. :tools es un JSON serializado (lista de nombres de tools).
-- El SDK debe pasar SIEMPRE todos los binds (los valores no modificados con su valor actual).
UPDATE ai_agents_agent
SET name             = :name,
    description      = :description,
    agent_type       = :agent_type,
    system_prompt    = :system_prompt,
    tools            = :tools,
    max_iterations   = :max_iterations,
    model_preference = :model_preference,
    is_active        = :is_active,
    updated_by       = :current_user_id,
    updated_at       = :now
WHERE id = :agent_id AND hub_id = :hub_id AND is_deleted = 0;
