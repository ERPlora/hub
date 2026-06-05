-- Edición de paquete (campos escalares; no toca las líneas). Portado de
-- PackageService.update_package. Para limpiar fixed_price, envía :fixed_price = NULL.
UPDATE services_package SET
  name           = :name,
  slug           = :slug,
  description    = :description,
  discount_type  = :discount_type,
  discount_value = :discount_value,
  fixed_price    = :fixed_price,
  validity_days  = :validity_days,
  max_uses       = :max_uses,
  is_active      = :is_active,
  is_featured    = :is_featured,
  updated_by     = :current_user_id,
  updated_at     = :now
WHERE id = :package_id AND hub_id = :hub_id AND is_deleted = 0;
