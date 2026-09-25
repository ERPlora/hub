-- Contract 2108 · migration 002 — retire the dead settings.
-- Written the "safe" way an author writes it first: DROP COLUMN IF EXISTS.
ALTER TABLE contract2108_settings DROP COLUMN IF EXISTS legacy_mode;
-- A column this install never had: IF EXISTS means "nothing to do", not "fail the update".
ALTER TABLE contract2108_settings DROP COLUMN IF EXISTS never_created;
