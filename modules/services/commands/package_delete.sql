-- Soft-delete de paquete (preserva el FK para histórico de ventas/bonos).
-- Portado de PackageService.delete_package. La cascada de soft-delete a las líneas
-- (services_packageitem) la coordina el SDK/handler → ver WASM-TODO.md.
UPDATE services_package
SET is_active = 0, is_deleted = 1, deleted_at = :now,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :package_id AND hub_id = :hub_id;
