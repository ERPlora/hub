-- Actualización de zona de reparto. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de DeliveryService.update_zone. El runtime pasa los valores actuales para los
-- campos no provistos (patch resuelto antes de llegar aquí); todos los binds son requeridos.
UPDATE delivery_zone
SET name           = :name,
    min_order      = :min_order,
    delivery_fee   = :delivery_fee,
    estimated_time = :estimated_time,
    is_active      = :is_active,
    zip_codes      = :zip_codes,
    max_radius_km  = :max_radius_km,
    sort_order     = :sort_order,
    updated_by     = :current_user_id,
    updated_at     = :now
WHERE id = :zone_id AND hub_id = :hub_id AND is_deleted = 0;
