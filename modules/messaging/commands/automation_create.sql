-- Alta de automatización CRM. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de AutomationService.create_automation. La evaluación del trigger contra eventos
-- (welcome/birthday/post_sale...) y la cola de ejecuciones van a WASM/runtime — ver WASM-TODO.
INSERT INTO messaging_automation
  (id, hub_id, name, description, trigger, channel, template_id, delay_hours,
   is_active, conditions, total_sent,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :trigger, :channel, :template_id, :delay_hours,
   1, :conditions, 0,
   0, :current_user_id, :current_user_id, :now, :now);
