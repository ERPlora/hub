-- Borrado lógico (soft-delete) de una estación. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de KitchenStationService.delete_station. Las guardas previas (no debe tener
-- enrutados activos ni líneas en curso) se validan en el handler WASM antes de invocar esto.
UPDATE kitchen_orders_station
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :station_id AND hub_id = :hub_id AND is_deleted = 0;
