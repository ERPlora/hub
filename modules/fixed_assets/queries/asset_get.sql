-- Detalle de un activo fijo concreto. Runtime inyecta :hub_id.
-- Portado de FixedAssetService.get_asset (la cabecera del activo). El historial de
-- amortizaciones y la baja se obtienen con depreciations_list / disposal_get.
SELECT id, asset_number, code, name, description, asset_category,
       acquisition_date, acquisition_cost, useful_life_years, depreciation_method,
       residual_value, accumulated_depreciation, current_book_value, status,
       location_ref, supplier_ref, created_at
FROM fixed_assets_asset
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :asset_id;
