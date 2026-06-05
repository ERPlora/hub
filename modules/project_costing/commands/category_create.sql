-- Alta de categoría de coste. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ProjectCostingService.create_category (code único por hub — lo garantiza
-- el índice uq_pc_category_hub_code). La validación de code/name la hace el JSON Schema.
-- :parent_id puede ser NULL (categoría raíz). La verificación de que el parent existe
-- y pertenece al hub es responsabilidad del runtime (FK + validación de tenancy).
INSERT INTO project_costing_category
  (id, hub_id, code, name, parent_id, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :parent_id, 1,
   0, :current_user_id, :current_user_id, :now, :now);
