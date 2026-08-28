-- Inventory · 003 (Postgres / Aurora cloud) — ADR-0085 (supersede ADR-0066): equivalente a
-- migrations/sqlite/003_tax_category_key.sql. Renombra `tax_rate_id` → `tax_category_key`
-- (clave de categoría fiscal canónica, no referencia a `taxes_rate.id`) en producto y
-- categoría. Mismo tipo TEXT, sin FK. Migración ADITIVA (no se edita 001/002).
ALTER TABLE inventory_product  RENAME COLUMN tax_rate_id TO tax_category_key;
ALTER TABLE inventory_category RENAME COLUMN tax_rate_id TO tax_category_key;
