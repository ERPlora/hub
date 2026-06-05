-- Actualización de estación. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de KitchenStationService.update_station. COALESCE(:x, col) deja sin tocar los
-- campos no enviados (el SDK pasa NULL para "no cambiar"; is_active se pasa 0/1).
UPDATE kitchen_orders_station
SET name         = COALESCE(:name, name),
    color        = COALESCE(:color, color),
    icon         = COALESCE(:icon, icon),
    printer_name = COALESCE(:printer_name, printer_name),
    is_active    = COALESCE(:is_active, is_active),
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :station_id AND hub_id = :hub_id AND is_deleted = 0;
