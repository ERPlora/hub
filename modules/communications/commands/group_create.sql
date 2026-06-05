-- Alta de grupo de enrutado. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO communications_group
  (id, hub_id, name, description, icon, color, is_active, is_default, is_system,
   source, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :icon, :color, :is_active, :is_default, 0,
   'custom', 0, :current_user_id, :current_user_id, :now, :now);
