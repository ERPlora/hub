-- Alta de categoría de gasto. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ExpenseService.create_category (code único por hub — lo garantiza el índice).
-- :parent_id puede ser NULL (categoría raíz) o el id de la categoría padre.
INSERT INTO expenses_category
  (id, hub_id, code, name, description, parent_id, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :parent_id, 1,
   0, :current_user_id, :current_user_id, :now, :now);
