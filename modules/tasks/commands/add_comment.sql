-- Añade un comentario a una tarea. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TaskService.add_comment. El comment no vacío lo valida el JSON Schema (minLength).
-- La existencia de la tarea referenciada (task_id) la garantiza la FK + el SDK previa al alta.
INSERT INTO tasks_comment
  (id, hub_id, task_id, author_ref, comment,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :task_id, :author_ref, :comment,
   0, :current_user_id, :current_user_id, :now, :now);
