-- Estado del asistente de setup para el hub (fila singleton). Runtime inyecta :hub_id.
-- Portado de setup.services.get_state. Devuelve a lo sumo una fila; el SDK/UI trata
-- "sin fila" como status implícito 'pending'.
SELECT id, status, template_key, answers, error_message, created_at, updated_at
FROM setup_state
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
