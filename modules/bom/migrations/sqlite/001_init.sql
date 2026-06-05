-- BOM (Bills of Materials) · esquema inicial (SQLite). Portado de modules/m_bom/models.py.
-- Modelos: BOM (receta versionada de un producto, ciclo de vida draft→active→obsolete,
-- un único default por product_ref) y BOMComponent (línea de la receta: o bien apunta a
-- un componente hoja (component_ref) o a una sub-BOM (sub_bom_id) para expansión multinivel).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- BOM: receta versionada para un producto.
-- code es único por hub. status sigue el ciclo draft→active→obsolete.
-- Solo una BOM por product_ref puede tener is_default=1 (lo impone el handler WASM set_as_default).
CREATE TABLE IF NOT EXISTS bom_bom (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    product_ref     TEXT NOT NULL,                    -- ref suelta al producto (sin FK)
    version         TEXT NOT NULL DEFAULT '1.0',
    status          TEXT NOT NULL DEFAULT 'draft',    -- draft|active|obsolete
    is_default      INTEGER NOT NULL DEFAULT 0,
    effective_from  TEXT,                             -- ISO YYYY-MM-DD o NULL
    effective_to    TEXT,                             -- ISO YYYY-MM-DD o NULL
    notes           TEXT NOT NULL DEFAULT '',
    approved_by_ref TEXT NOT NULL DEFAULT '',
    approved_at     TEXT,                             -- ISO datetime o NULL
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bom_hub_code        ON bom_bom (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_bom_hub_product     ON bom_bom (hub_id, product_ref);
CREATE INDEX        IF NOT EXISTS ix_bom_hub_status      ON bom_bom (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_bom_hub_default     ON bom_bom (hub_id, product_ref, is_default);
CREATE INDEX        IF NOT EXISTS idx_bom_bom_hub        ON bom_bom (hub_id, is_deleted);

-- BOMComponent: línea de la BOM. O referencia un componente hoja (component_ref) o
-- una sub-BOM (sub_bom_id) que el explosionado expande recursivamente.
-- quantity es por 1 unidad del padre; scrap_pct (0-100) son mermas del proceso.
CREATE TABLE IF NOT EXISTS bom_component (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    bom_id        TEXT NOT NULL,                      -- BOM padre
    component_ref TEXT NOT NULL,                      -- ref suelta (código producto, SKU…)
    quantity      NUMERIC NOT NULL DEFAULT 1.0000,    -- cantidad por 1 unidad del padre
    unit          TEXT NOT NULL DEFAULT 'each',
    scrap_pct     NUMERIC NOT NULL DEFAULT 0.00,      -- merma % (0-100)
    is_optional   INTEGER NOT NULL DEFAULT 0,
    sub_bom_id    TEXT,                               -- si !=NULL, expande otra BOM (multinivel)
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (bom_id)     REFERENCES bom_bom (id) ON DELETE CASCADE,
    FOREIGN KEY (sub_bom_id) REFERENCES bom_bom (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_bom_comp_bom        ON bom_component (bom_id);
CREATE INDEX IF NOT EXISTS ix_bom_comp_sub        ON bom_component (sub_bom_id);
CREATE INDEX IF NOT EXISTS idx_bom_component_hub  ON bom_component (hub_id, is_deleted);
