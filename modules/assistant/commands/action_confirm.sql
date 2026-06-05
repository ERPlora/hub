-- Marca un log de acción como confirmado por el usuario. Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado de confirm_action. NOTA: este UPDATE sólo cambia
-- el flag de confirmación + el resultado; la EJECUCIÓN real de la tool confirmada y
-- la reanudación del bucle agéntico (function_call_output) las hace el handler/runtime
-- — ver WASM-TODO §confirm/cancel. Sólo el dueño del log puede confirmarlo.
UPDATE assistant_action_log
SET confirmed = 1,
    success = :success,
    result = :result,
    error_message = :error_message,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :log_id
  AND created_by = :current_user_id
  AND confirmed = 0;
