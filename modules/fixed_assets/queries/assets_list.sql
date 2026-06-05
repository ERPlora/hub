-- Lista de activos fijos del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de FixedAssetService.list_assets. Los binds :status y :category son opcionales:
-- '' = sin filtro. Orden descendente por fecha de alta.
SELECT id, asset_number, code, name, description, asset_category,
       acquisition_date, acquisition_cost, useful_life_years, depreciation_method,
       residual_value, accumulated_depreciation, current_book_value, status,
       location_ref, supplier_ref, created_at
FROM fixed_assets_asset
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status   = '' OR status         = :status)
  AND (:category = '' OR asset_category = :category)
ORDER BY created_at DESC
LIMIT :limit;
