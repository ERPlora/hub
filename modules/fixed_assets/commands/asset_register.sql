-- Alta de activo fijo. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de FixedAssetService.register_asset (parte declarativa).
-- :asset_number lo provee el handler WASM (generate_asset_number, FA-YYYYMMDD-NNNN) y la
-- unicidad de code por hub la garantiza el índice ix_fa_hub_code. La validación de método/
-- importes y el cálculo inicial de current_book_value (= acquisition_cost) van en WASM-TODO.
INSERT INTO fixed_assets_asset
  (id, hub_id, asset_number, code, name, description, asset_category,
   acquisition_date, acquisition_cost, useful_life_years, depreciation_method,
   residual_value, accumulated_depreciation, current_book_value, status,
   location_ref, supplier_ref,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :asset_number, :code, :name, :description, :asset_category,
   :acquisition_date, :acquisition_cost, :useful_life_years, :depreciation_method,
   :residual_value, 0, :current_book_value, 'active',
   :location_ref, :supplier_ref,
   0, :current_user_id, :current_user_id, :now, :now);
