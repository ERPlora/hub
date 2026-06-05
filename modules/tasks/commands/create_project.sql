-- Alta de proyecto de tareas. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TaskService.create_project. code único por hub lo garantiza el índice
-- ix_task_project_hub_code (el SDK comprueba duplicado antes para dar un error amable).
INSERT INTO tasks_project
  (id, hub_id, code, name, color, is_active, owner_ref,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :color, 1, :owner_ref,
   0, :current_user_id, :current_user_id, :now, :now);
