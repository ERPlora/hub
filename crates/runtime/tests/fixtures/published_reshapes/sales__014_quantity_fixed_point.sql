-- 014 — ADR-0147: cantidades en punto fijo entero, escala GLOBAL 10⁶ (0,5 kg = 500000) + contexto
-- de unidades CONGELADO en la línea (§2.4, opción A). Ver el comentario largo en el dialecto
-- sqlite; aquí Postgres SÍ respeta el tipo declarado y basta el ALTER (sin reconstruir tablas).
--
-- EL DINERO NO SE TOCA: unit_price/net_amount/tax_amount/line_total siguen siendo céntimos
-- enteros (ADR-0123). ROUND(q × 10⁶), no ROUND(q) × 10⁶: las líneas históricas pueden traer 0,5
-- del arreglo parcial previo y ese medio kilo vendido es un hecho fiscal que hay que conservar.

-- ── sales_sale_item ─────────────────────────────────────────────────────────────────────────
ALTER TABLE sales_sale_item ALTER COLUMN quantity TYPE BIGINT USING ROUND(quantity * 1000000)::BIGINT;
ALTER TABLE sales_sale_item ALTER COLUMN quantity SET DEFAULT 1000000;

ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS unit_code            TEXT   NOT NULL DEFAULT 'ud';
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS unit_name            TEXT   NOT NULL DEFAULT '';
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS factor_num           BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS factor_den           BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS increment_value      BIGINT NOT NULL DEFAULT 1000000;
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS price_quantity_value BIGINT NOT NULL DEFAULT 1000000;
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS pricing_unit_code    TEXT   NOT NULL DEFAULT 'ud';
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS pricing_unit_name    TEXT   NOT NULL DEFAULT '';
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS pricing_factor_num   BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sales_sale_item ADD COLUMN IF NOT EXISTS pricing_factor_den   BIGINT NOT NULL DEFAULT 1;

-- ── sales_order_item ────────────────────────────────────────────────────────────────────────
ALTER TABLE sales_order_item ALTER COLUMN quantity TYPE BIGINT USING ROUND(quantity * 1000000)::BIGINT;
ALTER TABLE sales_order_item ALTER COLUMN quantity SET DEFAULT 1000000;

ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS unit_code            TEXT   NOT NULL DEFAULT 'ud';
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS unit_name            TEXT   NOT NULL DEFAULT '';
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS factor_num           BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS factor_den           BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS increment_value      BIGINT NOT NULL DEFAULT 1000000;
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS price_quantity_value BIGINT NOT NULL DEFAULT 1000000;
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS pricing_unit_code    TEXT   NOT NULL DEFAULT 'ud';
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS pricing_unit_name    TEXT   NOT NULL DEFAULT '';
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS pricing_factor_num   BIGINT NOT NULL DEFAULT 1;
ALTER TABLE sales_order_item ADD COLUMN IF NOT EXISTS pricing_factor_den   BIGINT NOT NULL DEFAULT 1;
