-- Contract 1137 · migration 002 — retire the addon table.
-- The feature moved into the core; this file is the way the table stops being used.
DROP TABLE IF EXISTS contract1137_addon;
