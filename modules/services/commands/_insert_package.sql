-- Inserción de la cabecera de un paquete usada por el handler WASM create_package.
-- El handler aporta :package_id (de new_ids) + slug. Runtime inyecta :hub_id,
-- :current_user_id, :now. Las líneas se insertan con services._insert_package_item.
INSERT INTO services_package
  (id, hub_id, name, slug, description, discount_type, discount_value, fixed_price,
   validity_days, max_uses, sort_order, is_active, is_featured,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:package_id, :hub_id, :name, :slug, :description, :discount_type, :discount_value, :fixed_price,
   :validity_days, :max_uses, :sort_order, :is_active, :is_featured,
   0, :current_user_id, :current_user_id, :now, :now);
