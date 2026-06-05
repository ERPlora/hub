-- Stock Sync · esquema inicial (SQLite). Portado fielmente de old_modules/m_stock_sync/models.py.
-- Modelos: StockChannel (endpoint de sincronización), StockSyncRun (sesión de sync entre dos
-- canales), StockSyncItem (línea por producto dentro de un run) y StockConflict (divergencia de
-- cantidades pendiente de resolución).
-- El StockSyncCounter legacy (secuencia atómica por hub+día para run_number) NO se materializa
-- como tabla de negocio: en hub-next es una capacidad del runtime (UPSERT counter) invocada por
-- el handler WASM — ver WASM-TODO.md.
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Canal de sincronización: endpoint registrado (hub local, tienda online, marketplace...).
-- code es único por hub y es el identificador estable referenciado por runs y conflictos.
CREATE TABLE IF NOT EXISTS stock_sync_channel (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    code          TEXT NOT NULL,
    name          TEXT NOT NULL,
    channel_type  TEXT NOT NULL DEFAULT 'hub',   -- hub|online_store|amazon|ebay|etsy|manual
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_sync_at  TEXT,                           -- ISO datetime o NULL
    settings      TEXT NOT NULL DEFAULT '{}',     -- JSON libre con credenciales/config del canal
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_stock_sync_channel_hub_code   ON stock_sync_channel (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_stock_sync_channel_hub_type   ON stock_sync_channel (hub_id, channel_type);
CREATE INDEX        IF NOT EXISTS ix_stock_sync_channel_hub_active ON stock_sync_channel (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_stock_sync_channel_hub       ON stock_sync_channel (hub_id, is_deleted);

-- Sesión de sincronización entre dos canales (source → target).
-- run_number es único por hub (formato SS-YYYYMMDD-NNNN, generado por el runtime).
CREATE TABLE IF NOT EXISTS stock_sync_run (
    id                 TEXT PRIMARY KEY,
    hub_id             TEXT NOT NULL,
    run_number         TEXT NOT NULL,
    source_channel_id  TEXT NOT NULL,
    target_channel_id  TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'running',  -- running|completed|failed
    started_at         TEXT NOT NULL,
    completed_at       TEXT,
    items_synced       INTEGER NOT NULL DEFAULT 0,
    conflicts_count    INTEGER NOT NULL DEFAULT 0,
    error_log          TEXT NOT NULL DEFAULT '',
    is_deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at         TEXT,
    created_by         TEXT,
    updated_by         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT,
    FOREIGN KEY (source_channel_id) REFERENCES stock_sync_channel (id) ON DELETE RESTRICT,
    FOREIGN KEY (target_channel_id) REFERENCES stock_sync_channel (id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_stock_sync_run_hub_number  ON stock_sync_run (hub_id, run_number);
CREATE INDEX        IF NOT EXISTS ix_stock_sync_run_hub_status  ON stock_sync_run (hub_id, status);
CREATE INDEX        IF NOT EXISTS ix_stock_sync_run_hub_started ON stock_sync_run (hub_id, started_at);
CREATE INDEX        IF NOT EXISTS idx_stock_sync_run_hub        ON stock_sync_run (hub_id, is_deleted);

-- Línea por producto tocada por un run de sincronización.
CREATE TABLE IF NOT EXISTS stock_sync_item (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    run_id           TEXT NOT NULL,
    product_ref      TEXT NOT NULL,
    source_quantity  NUMERIC NOT NULL DEFAULT 0,
    target_quantity  NUMERIC NOT NULL DEFAULT 0,
    action           TEXT NOT NULL DEFAULT 'push',   -- push|pull|skip|conflict
    resolved_at      TEXT,
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT,
    FOREIGN KEY (run_id) REFERENCES stock_sync_run (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_stock_sync_item_run         ON stock_sync_item (run_id);
CREATE INDEX IF NOT EXISTS ix_stock_sync_item_hub_product ON stock_sync_item (hub_id, product_ref);
CREATE INDEX IF NOT EXISTS idx_stock_sync_item_hub        ON stock_sync_item (hub_id, is_deleted);

-- Conflicto: divergencia de cantidades entre dos canales pendiente de resolución.
CREATE TABLE IF NOT EXISTS stock_sync_conflict (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    product_ref          TEXT NOT NULL,
    source_channel_id    TEXT NOT NULL,
    target_channel_id    TEXT NOT NULL,
    source_quantity      NUMERIC NOT NULL DEFAULT 0,
    target_quantity      NUMERIC NOT NULL DEFAULT 0,
    detected_at          TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'open',   -- open|resolved|ignored
    resolution_strategy  TEXT NOT NULL DEFAULT '',       -- use_source|use_target|manual|ignore|''
    resolved_at          TEXT,
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    FOREIGN KEY (source_channel_id) REFERENCES stock_sync_channel (id) ON DELETE RESTRICT,
    FOREIGN KEY (target_channel_id) REFERENCES stock_sync_channel (id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_stock_sync_conflict_hub_status  ON stock_sync_conflict (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_stock_sync_conflict_hub_product ON stock_sync_conflict (hub_id, product_ref);
CREATE INDEX IF NOT EXISTS ix_stock_sync_conflict_hub_source  ON stock_sync_conflict (hub_id, source_channel_id);
CREATE INDEX IF NOT EXISTS idx_stock_sync_conflict_hub        ON stock_sync_conflict (hub_id, is_deleted);
