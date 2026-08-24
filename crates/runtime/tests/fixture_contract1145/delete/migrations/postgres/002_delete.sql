-- Contract 1145 · migration 002 — drop the legacy rows now that the flag is gone.
DELETE FROM contract1145_thing WHERE legacy = 'yes';
