-- Alta de categoría del escaparate. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de StoreService.create_category. El slug único por hub lo garantiza el índice;
-- la validación de que :parent_id exista (cuando no es '') va a WASM/runtime — ver WASM-TODO.
-- :parent_id = '' se almacena como NULL (sin padre).
INSERT INTO online_store_category
  (id, hub_id, slug, name, parent_id, description, is_published, "order",
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :slug, :name,
   NULLIF(:parent_id, ''), '', 0, 0,
   0, :current_user_id, :current_user_id, :now, :now);
