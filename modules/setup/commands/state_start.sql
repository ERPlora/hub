-- Inicia (o reinicia) el asistente: marca status='in_progress', guarda plantilla + respuestas.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Portado de setup.services.apply_template
-- (parte de bookkeeping del estado; la orquestación pesada va a WASM — ver WASM-TODO.md).
-- Upsert sobre el singleton (hub_id, is_deleted) único: si ya existe, actualiza la fila.
INSERT INTO setup_state
  (id, hub_id, status, template_key, answers, error_message,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, 'in_progress', :template_key, :answers, '',
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (hub_id, is_deleted) DO UPDATE SET
  status        = 'in_progress',
  template_key  = excluded.template_key,
  answers       = excluded.answers,
  error_message = '',
  updated_by    = :current_user_id,
  updated_at    = :now;
