-- Desactivación lógica de un agente (is_active = 0; NO borra). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de AgentService.deactivate_agent.
UPDATE ai_agents_agent
SET is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :agent_id AND hub_id = :hub_id AND is_deleted = 0;
