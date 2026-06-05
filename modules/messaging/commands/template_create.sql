-- Alta de plantilla. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TemplateService.create_template. La validación de variables {{...}} desconocidas
-- (warning no bloqueante) va a WASM/runtime — ver WASM-TODO.
INSERT INTO messaging_template
  (id, hub_id, name, channel, category, subject, body, is_active, is_system,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :channel, :category, :subject, :body, 1, 0,
   0, :current_user_id, :current_user_id, :now, :now);
