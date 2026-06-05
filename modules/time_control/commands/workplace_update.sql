-- Actualización de centro de trabajo (scope hub_id). Runtime inyecta :current_user_id, :now.
-- Portado de WorkplaceUpdate. Patrón COALESCE: cada bind opcional NULL conserva el valor actual.
UPDATE time_control_workplace
SET name          = COALESCE(:name, name),
    address       = COALESCE(:address, address),
    latitude      = COALESCE(:latitude, latitude),
    longitude     = COALESCE(:longitude, longitude),
    radius_meters = COALESCE(:radius_meters, radius_meters),
    is_active     = COALESCE(:is_active, is_active),
    is_default    = COALESCE(:is_default, is_default),
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :workplace_id AND hub_id = :hub_id AND is_deleted = 0;
