-- Soft-delete de servicio (coherente con el contrato de fila §2.5).
-- Portado de ServiceCatalogService.delete_service. El bloqueo por citas activas
-- (appointments) es lógica cross-módulo → ver WASM-TODO.md.
UPDATE services_service
SET is_deleted = 1, deleted_at = :now, is_active = 0,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :service_id AND hub_id = :hub_id;
