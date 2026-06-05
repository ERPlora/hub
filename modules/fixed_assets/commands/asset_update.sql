-- Actualización de campos editables de un activo. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de FixedAssetService.update_asset (campos whitelisteados). El recálculo de
-- current_book_value cuando cambian acquisition_cost/residual_value se resuelve en WASM
-- (asset_recompute_book_value) — ver WASM-TODO. Aquí se persisten los valores ya validados.
UPDATE fixed_assets_asset
SET name                = :name,
    description         = :description,
    asset_category      = :asset_category,
    acquisition_date    = :acquisition_date,
    acquisition_cost    = :acquisition_cost,
    useful_life_years   = :useful_life_years,
    depreciation_method = :depreciation_method,
    residual_value      = :residual_value,
    status              = :status,
    location_ref        = :location_ref,
    supplier_ref        = :supplier_ref,
    current_book_value  = :current_book_value,
    updated_by          = :current_user_id,
    updated_at          = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :asset_id;
