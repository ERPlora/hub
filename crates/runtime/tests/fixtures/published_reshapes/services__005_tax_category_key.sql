-- Services · migración aditiva 003 (Postgres / Aurora cloud). Equivalente a
-- migrations/sqlite/003_tax_category_key.sql. ADR-0085 (supersede ADR-0066): el enlace
-- fiscal deja de ser una REFERENCIA a un tipo (`taxes_rate.id`) y pasa a ser una CLAVE DE
-- CATEGORÍA FISCAL canónica (`tax_category_key`). Unifica con inventory. Sin FK cross-módulo.

-- services_service: `tax_rate_id` → `tax_category_key`.
ALTER TABLE services_service RENAME COLUMN tax_rate_id TO tax_category_key;

-- services_settings: `default_tax_rate_id` → `default_tax_category_key`.
ALTER TABLE services_settings RENAME COLUMN default_tax_rate_id TO default_tax_category_key;
