-- Kernel fixture · migration 003 (backfill) — rows the previous version wrote, rewritten in place.
-- DML over the module's own table and nothing else: a `backfill` may not touch the schema.
UPDATE kfx_item SET name = btrim(name) WHERE name <> btrim(name);
