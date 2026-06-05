-- Agentes del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de AgentService.list_agents. Filtros opcionales: active_only (1/0) y agent_type.
-- (:agent_type = '' significa sin filtro.)
SELECT id, code, name, description, agent_type, system_prompt, tools,
       max_iterations, model_preference, is_active, total_runs, total_cost_eur,
       created_at
FROM ai_agents_agent
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
  AND (:agent_type = '' OR agent_type = :agent_type)
ORDER BY created_at DESC;
