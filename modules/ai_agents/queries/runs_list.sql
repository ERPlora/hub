-- Runs recientes del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de AgentService.list_runs. Filtros opcionales: agent_id y status ('' = sin filtro).
-- :limit acota el número de filas devueltas.
SELECT id, run_number, agent_id, trigger_type, input_query, status,
       iterations_used, tokens_used, cost_eur, started_at, completed_at,
       final_output, error_message, created_at
FROM ai_agents_run
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:agent_id = '' OR agent_id = :agent_id)
  AND (:status   = '' OR status   = :status)
ORDER BY created_at DESC
LIMIT :limit;
