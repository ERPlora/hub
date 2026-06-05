-- Un run concreto por id. Runtime inyecta :hub_id.
-- Portado de AgentService.get_run (cabecera; los pasos se obtienen con ai_agents.steps.list).
SELECT id, run_number, agent_id, trigger_type, input_query, status,
       iterations_used, tokens_used, cost_eur, started_at, completed_at,
       final_output, error_message, created_at
FROM ai_agents_run
WHERE id = :run_id AND hub_id = :hub_id AND is_deleted = 0;
