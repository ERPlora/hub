-- Lista de proyectos de tareas. Runtime inyecta :hub_id.
-- Portado de TaskService.list_projects. :active_only = 1 limita a proyectos activos;
-- cualquier otro valor (0/'') devuelve todos.
SELECT id, code, name, color, is_active, owner_ref, created_at
FROM tasks_project
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
