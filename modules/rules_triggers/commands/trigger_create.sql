-- Alta de trigger. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de RulesService.create_trigger. La validación de event_type (enum) la cubre el
-- JSON Schema; el code único por hub lo garantiza el índice ix_rt_trg_hub_code.
INSERT INTO rules_triggers_trigger
  (id, hub_id, code, name, event_type, entity_filter, is_active,
   last_fired_at, fire_count,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :event_type, :entity_filter, 1,
   NULL, 0,
   0, :current_user_id, :current_user_id, :now, :now);
