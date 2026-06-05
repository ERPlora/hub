-- Payroll · esquema inicial (SQLite). Portado fielmente de old_modules/m_payroll/models.py.
-- Modelos: PayrollSettings (singleton por hub), PayrollConcept (plantilla de devengo/deducción),
-- Payslip (nómina por empleado y periodo) y PayslipLine (línea de la nómina).
-- Contrato de fila estándar de hub-next (§2.5): hub_id + soft-delete + auditoría.
-- La lógica de cálculo (collectors, deducciones, balance de totales) NO va aquí → ver WASM-TODO.md.

-- Configuración de nómina (una fila por hub). Multiplicadores y tipos de retención.
CREATE TABLE IF NOT EXISTS payroll_settings (
    id                        TEXT PRIMARY KEY,
    hub_id                    TEXT NOT NULL,
    default_pay_period        TEXT NOT NULL DEFAULT 'monthly',  -- weekly|biweekly|monthly
    currency                  TEXT NOT NULL DEFAULT 'EUR',
    overtime_multiplier       NUMERIC NOT NULL DEFAULT 1.50,
    night_shift_multiplier    NUMERIC NOT NULL DEFAULT 1.25,
    holiday_multiplier        NUMERIC NOT NULL DEFAULT 2.00,
    social_security_rate      NUMERIC NOT NULL DEFAULT 6.35,   -- % cuota empleado
    income_tax_rate           NUMERIC NOT NULL DEFAULT 15.00,  -- % IRPF
    auto_calculate_deductions INTEGER NOT NULL DEFAULT 1,
    is_deleted                INTEGER NOT NULL DEFAULT 0,
    deleted_at                TEXT,
    created_by                TEXT,
    updated_by                TEXT,
    created_at                TEXT NOT NULL,
    updated_at                TEXT
);
-- Singleton por hub (uq_payroll_settings_hub en el modelo legacy).
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_settings_hub ON payroll_settings (hub_id);
CREATE INDEX        IF NOT EXISTS idx_payroll_settings_hub ON payroll_settings (hub_id, is_deleted);

-- Concepto de nómina: plantilla de devengo (earning) o deducción (deduction).
-- Importe fijo o porcentaje; sirve para componer líneas de nómina.
CREATE TABLE IF NOT EXISTS payroll_concept (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    type          TEXT NOT NULL DEFAULT 'earning',  -- earning|deduction
    is_percentage INTEGER NOT NULL DEFAULT 0,
    amount        NUMERIC NOT NULL DEFAULT 0,
    percentage    NUMERIC NOT NULL DEFAULT 0,
    is_taxable    INTEGER NOT NULL DEFAULT 1,
    is_active     INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_payroll_concept_hub_type ON payroll_concept (hub_id, type);
CREATE INDEX IF NOT EXISTS idx_payroll_concept_hub     ON payroll_concept (hub_id, is_deleted);

-- Nómina (payslip) de un empleado para un periodo. employee_id referencia a staff
-- (módulo dependiente); NO se hace FK cross-módulo: cada módulo OWNea sus tablas.
-- breakdown es JSON (desglose de devengos/deducciones para el recibo).
CREATE TABLE IF NOT EXISTS payroll_payslip (
    id               TEXT PRIMARY KEY,
    hub_id           TEXT NOT NULL,
    employee_id      TEXT NOT NULL,
    employee_name    TEXT NOT NULL,
    period_start     TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    period_end       TEXT NOT NULL,                 -- ISO YYYY-MM-DD
    gross_salary     NUMERIC NOT NULL DEFAULT 0,
    total_earnings   NUMERIC NOT NULL DEFAULT 0,
    total_deductions NUMERIC NOT NULL DEFAULT 0,
    net_salary       NUMERIC NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'draft', -- draft|confirmed|approved|paid|cancelled
    paid_date        TEXT,                          -- ISO YYYY-MM-DD o NULL
    payment_method   TEXT,
    notes            TEXT NOT NULL DEFAULT '',
    breakdown        TEXT NOT NULL DEFAULT '{}',    -- JSON: {earnings:[...], deductions:[...]}
    is_deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at       TEXT,
    created_by       TEXT,
    updated_by       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_payroll_payslip_hub_employee ON payroll_payslip (hub_id, employee_id);
CREATE INDEX IF NOT EXISTS ix_payroll_payslip_hub_status   ON payroll_payslip (hub_id, status);
CREATE INDEX IF NOT EXISTS ix_payroll_payslip_hub_period   ON payroll_payslip (hub_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_payroll_payslip_hub         ON payroll_payslip (hub_id, is_deleted);

-- Línea de nómina: devengo o deducción concreta dentro de un payslip.
-- source_module/source_id dan trazabilidad (time_control/timesheets/commissions/contract).
CREATE TABLE IF NOT EXISTS payroll_payslip_line (
    id            TEXT PRIMARY KEY,
    hub_id        TEXT NOT NULL,
    payslip_id    TEXT NOT NULL,
    concept_name  TEXT NOT NULL,
    type          TEXT NOT NULL DEFAULT 'earning',  -- earning|deduction
    amount        NUMERIC NOT NULL DEFAULT 0,
    is_percentage INTEGER NOT NULL DEFAULT 0,
    percentage    NUMERIC NOT NULL DEFAULT 0,
    base_amount   NUMERIC NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    source_module TEXT NOT NULL DEFAULT '',
    source_id     TEXT,
    quantity      NUMERIC NOT NULL DEFAULT 0,
    rate          NUMERIC NOT NULL DEFAULT 0,
    is_deleted    INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,
    created_by    TEXT,
    updated_by    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT,
    FOREIGN KEY (payslip_id) REFERENCES payroll_payslip (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_payroll_line_payslip ON payroll_payslip_line (hub_id, payslip_id);
CREATE INDEX IF NOT EXISTS idx_payroll_payslip_line_hub ON payroll_payslip_line (hub_id, is_deleted);
