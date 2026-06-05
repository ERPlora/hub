-- Inserción de una línea de paquete (paquete ↔ servicio) usada por el handler WASM
-- create_package, una op por línea. El handler aporta :item_id (de new_ids),
-- :package_id, :service_id, :quantity, :sort_order. Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado del bucle items[] de PackageService.create_package.
INSERT INTO services_packageitem
  (id, hub_id, package_id, service_id, quantity, sort_order,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:item_id, :hub_id, :package_id, :service_id, :quantity, :sort_order,
   0, :current_user_id, :current_user_id, :now, :now);
