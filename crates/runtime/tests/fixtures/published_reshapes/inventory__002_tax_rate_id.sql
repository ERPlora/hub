-- Inventory · 002 (Postgres / Aurora cloud) — ADR-0066: equivalente a
-- migrations/sqlite/002_tax_rate_id.sql. Renombra `tax_class_id` → `tax_rate_id` en
-- producto y categoría (referencia a `taxes_rate.id`). Migración ADITIVA (no se edita 001).
ALTER TABLE inventory_product  RENAME COLUMN tax_class_id TO tax_rate_id;
ALTER TABLE inventory_category RENAME COLUMN tax_class_id TO tax_rate_id;
