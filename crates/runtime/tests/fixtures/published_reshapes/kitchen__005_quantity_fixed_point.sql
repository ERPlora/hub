-- ADR-0147 §2.1 — `kitchen_order_item.quantity` a punto fijo ENTERO escala 10⁶.
-- Ver migrations/sqlite/005. La 004 la había pasado a REAL (fraccionable); vuelve a entero,
-- ya reescalado.
ALTER TABLE kitchen_order_item ALTER COLUMN quantity TYPE BIGINT USING ROUND(quantity * 1000000)::BIGINT;
ALTER TABLE kitchen_order_item ALTER COLUMN quantity SET DEFAULT 1000000;
