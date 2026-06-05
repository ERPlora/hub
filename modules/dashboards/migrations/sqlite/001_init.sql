-- Dashboards · esquema inicial (SQLite). Portado fielmente de old_modules/m_dashboards/models.py.
-- Modelos: Dashboard (panel BI configurable), Widget (tarjeta/gráfico en la rejilla del panel),
-- DashboardShare (compartición con usuario/rol a nivel view|edit).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Panel BI configurable. code es identificador estable único por hub (menús/deep-links).
-- layout es JSON libre (rejilla rows/cols/breakpoints). owner_ref es un ref libre de usuario.
CREATE TABLE IF NOT EXISTS dashboards_dashboard (
    id                   TEXT PRIMARY KEY,
    hub_id               TEXT NOT NULL,
    code                 TEXT NOT NULL,
    name                 TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    layout               TEXT,                          -- JSON libre o NULL
    is_default           INTEGER NOT NULL DEFAULT 0,
    is_public            INTEGER NOT NULL DEFAULT 0,
    owner_ref            TEXT,                          -- ref libre de usuario (UUID) o NULL
    theme                TEXT NOT NULL DEFAULT 'light', -- light|dark|auto
    refresh_interval_sec INTEGER NOT NULL DEFAULT 0,    -- 0 = manual, >0 = auto-refresh (seg)
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    deleted_at           TEXT,
    created_by           TEXT,
    updated_by           TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_dash_hub_code      ON dashboards_dashboard (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_dash_hub_default   ON dashboards_dashboard (hub_id, is_default);
CREATE INDEX        IF NOT EXISTS ix_dash_hub_public    ON dashboards_dashboard (hub_id, is_public);
CREATE INDEX        IF NOT EXISTS ix_dash_hub_owner     ON dashboards_dashboard (hub_id, owner_ref);
CREATE INDEX        IF NOT EXISTS idx_dashboards_dashboard_hub ON dashboards_dashboard (hub_id, is_deleted);

-- Widget de un panel. widget_type selecciona el render (kpi_card|line_chart|bar_chart|
-- pie_chart|table|gauge|map). config = fuente de datos/consulta/display (JSON libre).
-- data_cache + cached_at memoizan el último payload calculado.
CREATE TABLE IF NOT EXISTS dashboards_widget (
    id           TEXT PRIMARY KEY,
    hub_id       TEXT NOT NULL,
    dashboard_id TEXT NOT NULL,
    widget_type  TEXT NOT NULL,                  -- kpi_card|line_chart|bar_chart|pie_chart|table|gauge|map
    title        TEXT NOT NULL,
    position_x   INTEGER NOT NULL DEFAULT 0,
    position_y   INTEGER NOT NULL DEFAULT 0,
    width        INTEGER NOT NULL DEFAULT 4,
    height       INTEGER NOT NULL DEFAULT 3,
    config       TEXT,                           -- JSON libre o NULL
    data_cache   TEXT,                           -- JSON libre o NULL (payload cacheado)
    cached_at    TEXT,
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    created_by   TEXT,
    updated_by   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT,
    FOREIGN KEY (dashboard_id) REFERENCES dashboards_dashboard (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_widget_hub_dashboard   ON dashboards_widget (hub_id, dashboard_id);
CREATE INDEX IF NOT EXISTS ix_widget_hub_type        ON dashboards_widget (hub_id, widget_type);
CREATE INDEX IF NOT EXISTS idx_dashboards_widget_hub ON dashboards_widget (hub_id, is_deleted);

-- Compartición de un panel con un usuario o rol. shared_with_ref es ref libre (UUID usuario
-- o nombre de rol). access_level es view|edit. shared_by_ref es el usuario que concedió.
CREATE TABLE IF NOT EXISTS dashboards_share (
    id              TEXT PRIMARY KEY,
    hub_id          TEXT NOT NULL,
    dashboard_id    TEXT NOT NULL,
    shared_with_ref TEXT NOT NULL,
    access_level    TEXT NOT NULL DEFAULT 'view',  -- view|edit
    shared_at       TEXT,
    shared_by_ref   TEXT,                           -- ref libre de usuario (UUID) o NULL
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT,
    created_by      TEXT,
    updated_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    FOREIGN KEY (dashboard_id) REFERENCES dashboards_dashboard (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_dash_share_hub_dashboard ON dashboards_share (hub_id, dashboard_id);
CREATE INDEX IF NOT EXISTS ix_dash_share_hub_target    ON dashboards_share (hub_id, shared_with_ref);
CREATE INDEX IF NOT EXISTS idx_dashboards_share_hub    ON dashboards_share (hub_id, is_deleted);
