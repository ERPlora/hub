-- Alta de regla de enrutado. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- :conditions y :auto_label se reciben ya serializados como JSON (TEXT).
INSERT INTO communications_routing_rule
  (id, hub_id, group_id, name, priority, is_active, conditions,
   auto_assign_to_id, auto_label, auto_priority,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :group_id, :name, :priority, :is_active, :conditions,
   :auto_assign_to_id, :auto_label, :auto_priority,
   0, :current_user_id, :current_user_id, :now, :now);
