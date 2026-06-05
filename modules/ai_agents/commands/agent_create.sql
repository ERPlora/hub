-- Alta de agente. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de AgentService.create_agent (code único por hub — lo garantiza el índice).
-- :tools es un JSON serializado (lista de nombres de tools).
INSERT INTO ai_agents_agent
  (id, hub_id, code, name, description, agent_type, system_prompt, tools,
   max_iterations, model_preference, is_active, total_runs, total_cost_eur,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :agent_type, :system_prompt, :tools,
   :max_iterations, :model_preference, 1, 0, 0,
   0, :current_user_id, :current_user_id, :now, :now);
