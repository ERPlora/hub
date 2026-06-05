-- El usuario opta por no usar el asistente: marca status='skipped'.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now. Portado de setup.services.skip_setup.
-- Upsert sobre el singleton: crea la fila si no existía (instalación sin on_install previo).
INSERT INTO setup_state
  (id, hub_id, status, template_key, answers, error_message,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, 'skipped', '', '{}', '',
   0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (hub_id, is_deleted) DO UPDATE SET
  status        = 'skipped',
  error_message = '',
  updated_by    = :current_user_id,
  updated_at    = :now;
