-- OLAP Cubes · esquema inicial (SQLite). Portado fielmente de old_modules/m_olap_cubes/models.py.
-- Modelos: OLAPCube (definición de cubo: tabla origen + dimensiones + medidas + filtros),
-- OLAPQuery (ejecución de una consulta multidimensional contra un cubo) y
-- OLAPCachedSlice (slice agregado memoizado para cortocircuitar rutas calientes).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- Las columnas JSON se guardan como TEXT (JSON serializado) en SQLite.

-- Cubo OLAP: definición multidimensional. code es único por hub.
-- dimensions = JSON list de {"field":..., "label":...}.
-- measures   = JSON list de {"field":..., "label":..., "agg":"sum|avg|count|max|min"}.
-- filters    = JSON con condiciones de filtro por defecto.
CREATE TABLE IF NOT EXISTS olap_cubes_cube (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    source_table TEXT NOT NULL,
    dimensions   TEXT NOT NULL DEFAULT '[]',   -- JSON list de dimensiones
    measures     TEXT NOT NULL DEFAULT '[]',   -- JSON list de medidas
    filters      TEXT NOT NULL DEFAULT '{}',   -- JSON con filtros por defecto
    is_active    INTEGER NOT NULL DEFAULT 1,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_olap_cube_hub_code   ON olap_cubes_cube (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_olap_cube_hub_active  ON olap_cubes_cube (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_olap_cubes_cube_hub  ON olap_cubes_cube (hub_id, is_deleted);

-- Consulta OLAP: una ejecución de query contra un cubo (auditable / re-ejecutable).
-- query_number = OLQ-YYYYMMDD-NNNN (contador por hub-día, lo genera el runtime/WASM).
-- dimensions_used/measures_used/filters_applied/result_cells = JSON serializado.
CREATE TABLE IF NOT EXISTS olap_cubes_query (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    cube_id           TEXT NOT NULL,
    query_number      TEXT NOT NULL,
    dimensions_used   TEXT NOT NULL DEFAULT '[]',  -- JSON list de campos dimensión
    measures_used     TEXT NOT NULL DEFAULT '[]',  -- JSON list de campos medida
    filters_applied   TEXT NOT NULL DEFAULT '{}',  -- JSON con filtros aplicados
    result_cells      TEXT NOT NULL DEFAULT '[]',  -- JSON list de filas agregadas
    result_count      INTEGER NOT NULL DEFAULT 0,
    executed_at       TEXT,
    executed_by_ref   TEXT,
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (cube_id) REFERENCES olap_cubes_cube (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_olap_query_hub_number      ON olap_cubes_query (hub_id, query_number);
CREATE INDEX        IF NOT EXISTS ix_olap_query_hub_cube        ON olap_cubes_query (hub_id, cube_id);
CREATE INDEX        IF NOT EXISTS ix_olap_query_hub_executed_at ON olap_cubes_query (hub_id, executed_at);
CREATE INDEX        IF NOT EXISTS idx_olap_cubes_query_hub      ON olap_cubes_query (hub_id, is_deleted);

-- Slice cacheado: agregación memoizada de un cubo.
-- slice_key = hash de dimensiones/medidas + filtros aplicados. Único por (hub, cube, key).
-- expires_at dispara invalidación perezosa; hit_count se incrementa en cada acierto.
CREATE TABLE IF NOT EXISTS olap_cubes_cached_slice (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    cube_id     TEXT NOT NULL,
    slice_key   TEXT NOT NULL,
    data        TEXT NOT NULL DEFAULT 'null',   -- JSON serializado (objeto o lista)
    computed_at TEXT,
    expires_at  TEXT,
    hit_count   INTEGER NOT NULL DEFAULT 0,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    FOREIGN KEY (cube_id) REFERENCES olap_cubes_cube (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_olap_slice_hub_cube_key    ON olap_cubes_cached_slice (hub_id, cube_id, slice_key);
CREATE INDEX        IF NOT EXISTS ix_olap_slice_hub_expires_at   ON olap_cubes_cached_slice (hub_id, expires_at);
CREATE INDEX        IF NOT EXISTS idx_olap_cubes_slice_hub       ON olap_cubes_cached_slice (hub_id, is_deleted);
