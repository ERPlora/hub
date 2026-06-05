-- Financial Statements · esquema inicial (SQLite). Portado fielmente de
-- modules/m_financial_statements/models.py.
-- Modelos: ReportTemplate (layout nombrado de un informe), ReportLineItem (línea de la
-- plantilla: qué cuentas suman/restan) y GeneratedReport (snapshot histórico calculado).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.

-- Plantilla de informe: layout nombrado para un tipo de informe financiero.
-- code es único por hub y es el identificador estable. structure es JSON libre
-- (secciones, metadatos de cabecera, opciones de display). report_type ∈
-- balance_sheet|profit_loss|cash_flow|custom.
CREATE TABLE IF NOT EXISTS financial_statements_template (
    id          TEXT PRIMARY KEY,
    hub_id      TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'custom',  -- balance_sheet|profit_loss|cash_flow|custom
    structure   TEXT NOT NULL DEFAULT '{}',      -- JSON libre: secciones / cabecera / display
    is_default  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    deleted_at  TEXT,
    created_by  TEXT,
    updated_by  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_fs_template_hub_code   ON financial_statements_template (hub_id, code);
CREATE INDEX        IF NOT EXISTS ix_fs_template_hub_type   ON financial_statements_template (hub_id, report_type);
CREATE INDEX        IF NOT EXISTS ix_fs_template_hub_active ON financial_statements_template (hub_id, is_active);
CREATE INDEX        IF NOT EXISTS idx_financial_statements_template_hub ON financial_statements_template (hub_id, is_deleted);

-- Línea de plantilla: o bien suma/resta cuentas concretas (account_codes con sign +1/-1),
-- o bien es una línea de subtotal (is_total=1) cuyo valor se calcula aguas abajo.
-- account_codes es JSON (lista de códigos de cuenta). item_order ordena dentro de la sección.
CREATE TABLE IF NOT EXISTS financial_statements_line_item (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    template_id   TEXT NOT NULL,
    section       TEXT NOT NULL,
    item_code     TEXT NOT NULL,
    item_label    TEXT NOT NULL,
    item_order    INTEGER NOT NULL DEFAULT 0,
    account_codes TEXT NOT NULL DEFAULT '[]',    -- JSON: lista de códigos de cuenta que alimentan la línea
    sign          INTEGER NOT NULL DEFAULT 1,    -- +1 suma, -1 resta (contra-cuentas)
    is_total      INTEGER NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (template_id) REFERENCES financial_statements_template (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_fs_line_template_section ON financial_statements_line_item (template_id, section);
CREATE INDEX IF NOT EXISTS ix_fs_line_template_order   ON financial_statements_line_item (template_id, item_order);
CREATE INDEX IF NOT EXISTS idx_financial_statements_line_item_hub ON financial_statements_line_item (hub_id, is_deleted);

-- Informe generado: snapshot de un informe calculado. data (JSON) guarda el output
-- renderizado (secciones, líneas, totales) para re-mostrarlo sin recalcular.
-- status ∈ draft|final. period_start/period_end acotan el periodo del informe.
CREATE TABLE IF NOT EXISTS financial_statements_generated (
    id                TEXT PRIMARY KEY,
    hub_id            TEXT NOT NULL,
    template_id       TEXT NOT NULL,
    report_type       TEXT NOT NULL DEFAULT 'custom',  -- balance_sheet|profit_loss|cash_flow|custom
    period_start      TEXT,                            -- ISO YYYY-MM-DD o NULL
    period_end        TEXT,                            -- ISO YYYY-MM-DD o NULL
    generated_at      TEXT,                            -- ISO timestamp del cálculo
    generated_by_ref  TEXT,                            -- ref libre al usuario que generó (sin FK)
    status            TEXT NOT NULL DEFAULT 'draft',   -- draft|final
    data              TEXT NOT NULL DEFAULT '{}',      -- JSON: snapshot de secciones/líneas/totales
    notes             TEXT NOT NULL DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_by        TEXT,
    updated_by        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT,
    FOREIGN KEY (template_id) REFERENCES financial_statements_template (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_fs_generated_hub_type   ON financial_statements_generated (hub_id, report_type);
CREATE INDEX IF NOT EXISTS ix_fs_generated_hub_period ON financial_statements_generated (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS ix_fs_generated_hub_status ON financial_statements_generated (hub_id, status);
CREATE INDEX IF NOT EXISTS idx_financial_statements_generated_hub ON financial_statements_generated (hub_id, is_deleted);
