-- Traza paso a paso de un run, ordenada por step_index. Runtime inyecta :hub_id.
-- Portado de la parte de pasos de AgentService.get_run (include_steps=True).
SELECT id, run_id, step_index, step_type, tool_name, content, tokens_used, occurred_at
FROM ai_agents_step
WHERE run_id = :run_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY step_index ASC;
