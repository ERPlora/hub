-- Edición de servicio (la UI envía el conjunto de campos editables, Tier 0/1).
-- Portado de ServiceCatalogService.update_service. NOTA: el aviso por citas activas
-- (appointments) que comprueba el legacy es lógica cross-módulo → ver WASM-TODO.md.
UPDATE services_service SET
  name             = :name,
  slug             = :slug,
  description      = :description,
  category_id      = :category_id,
  pricing_type     = :pricing_type,
  price            = :price,
  cost             = :cost,
  duration_minutes = :duration_minutes,
  is_bookable      = :is_bookable,
  is_active        = :is_active,
  sort_order       = :sort_order,
  updated_by       = :current_user_id,
  updated_at       = :now
WHERE id = :service_id AND hub_id = :hub_id AND is_deleted = 0;
