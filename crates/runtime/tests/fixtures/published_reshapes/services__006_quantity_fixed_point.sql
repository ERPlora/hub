-- ADR-0147 — sesiones de bono a punto fijo ENTERO escala 10⁶. Ver migrations/sqlite/006.
ALTER TABLE services_packageitem ALTER COLUMN quantity TYPE BIGINT USING (quantity::BIGINT * 1000000);
ALTER TABLE services_packageitem ALTER COLUMN quantity SET DEFAULT 1000000;
