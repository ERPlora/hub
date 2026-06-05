-- Fixed Assets · esquema inicial (SQLite). Portado fielmente de old_modules/m_fixed_assets/models.py.
-- Modelos: FixedAsset (activo de larga vida), DepreciationEntry (entrada de amortización por periodo)
-- y AssetDisposal (baja: venta/desguace/donación/pérdida).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Activo fijo (tangible o intangible) propiedad del hub.
-- asset_number se autogenera (FA-YYYYMMDD-NNNN, ver WASM-TODO); code es único por hub.
-- accumulated_depreciation y current_book_value son totales corrientes mantenidos por los commands.
CREATE TABLE IF NOT EXISTS fixed_assets_asset (
    id                       TEXT PRIMARY KEY,
    hub_id                   TEXT NOT NULL,
    asset_number             TEXT NOT NULL,
    code                     TEXT NOT NULL,
    name                     TEXT NOT NULL,
    description              TEXT NOT NULL DEFAULT '',
    asset_category           TEXT NOT NULL DEFAULT '',
    acquisition_date         TEXT,                            -- ISO YYYY-MM-DD o NULL
    acquisition_cost         NUMERIC NOT NULL DEFAULT 0,
    useful_life_years        INTEGER NOT NULL DEFAULT 0,
    depreciation_method      TEXT NOT NULL DEFAULT 'linear',  -- linear|declining|units_of_production
    residual_value           NUMERIC NOT NULL DEFAULT 0,
    accumulated_depreciation NUMERIC NOT NULL DEFAULT 0,
    current_book_value       NUMERIC NOT NULL DEFAULT 0,
    status                   TEXT NOT NULL DEFAULT 'active',   -- active|disposed|written_off|in_maintenance
    location_ref             TEXT NOT NULL DEFAULT '',
    supplier_ref             TEXT NOT NULL DEFAULT '',
    is_deleted               INTEGER NOT NULL DEFAULT 0,
    deleted_at               TEXT,
    created_by               TEXT,
    updated_by               TEXT,
    created_at               TEXT NOT NULL,
    updated_at               TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_fa_hub_code      ON fixed_assets_asset (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_fa_hub_status    ON fixed_assets_asset (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_fa_hub_number    ON fixed_assets_asset (hub_id, asset_number);
CREATE INDEX        IF NOT EXISTS ix_fa_hub_category  ON fixed_assets_asset (hub_id, asset_category);
CREATE INDEX        IF NOT EXISTS ix_fa_hub_acq_date  ON fixed_assets_asset (hub_id, acquisition_date);
CREATE INDEX        IF NOT EXISTS idx_fixed_assets_asset_hub ON fixed_assets_asset (hub_id, is_deleted);

-- Entrada de amortización: importe amortizado en un periodo contra un activo.
-- accumulated_after / book_value_after son fotos de los totales tras postear esta entrada.
CREATE TABLE IF NOT EXISTS fixed_assets_depreciation (
    id                  TEXT PRIMARY KEY,
    hub_id              TEXT NOT NULL,
    asset_id            TEXT NOT NULL,
    period_start        TEXT,                          -- ISO YYYY-MM-DD o NULL
    period_end          TEXT,                          -- ISO YYYY-MM-DD o NULL
    depreciation_amount NUMERIC NOT NULL DEFAULT 0,
    accumulated_after   NUMERIC NOT NULL DEFAULT 0,
    book_value_after    NUMERIC NOT NULL DEFAULT 0,
    posted              INTEGER NOT NULL DEFAULT 0,
    posted_at           TEXT,                          -- ISO datetime o NULL
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    deleted_at          TEXT,
    created_by          TEXT,
    updated_by          TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    FOREIGN KEY (asset_id) REFERENCES fixed_assets_asset (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_fa_dep_asset   ON fixed_assets_depreciation (asset_id);
CREATE INDEX IF NOT EXISTS ix_fa_dep_period  ON fixed_assets_depreciation (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS ix_fa_dep_posted  ON fixed_assets_depreciation (hub_id, posted);
CREATE INDEX IF NOT EXISTS idx_fixed_assets_depreciation_hub ON fixed_assets_depreciation (hub_id, is_deleted);

-- Baja de un activo fijo (venta/desguace/donación/pérdida).
-- gain_loss = sale_price - book_value (calculado en el command/WASM).
CREATE TABLE IF NOT EXISTS fixed_assets_disposal (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    asset_id      TEXT NOT NULL,
    disposal_date TEXT,                          -- ISO YYYY-MM-DD o NULL
    disposal_type TEXT NOT NULL DEFAULT 'sale',  -- sale|scrap|donation|loss
    sale_price    NUMERIC NOT NULL DEFAULT 0,
    gain_loss     NUMERIC NOT NULL DEFAULT 0,
    notes         TEXT NOT NULL DEFAULT '',
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (asset_id) REFERENCES fixed_assets_asset (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_fa_disp_asset ON fixed_assets_disposal (asset_id);
CREATE INDEX IF NOT EXISTS ix_fa_disp_date  ON fixed_assets_disposal (hub_id, disposal_date);
CREATE INDEX IF NOT EXISTS idx_fixed_assets_disposal_hub ON fixed_assets_disposal (hub_id, is_deleted);
