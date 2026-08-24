-- Contract 1145 · migration 002 — the feature moved into the core, so the table is emptied here.
-- The author writes this believing `kind: "contract"` keeps the rows recoverable, like a `DROP` does.
TRUNCATE contract1145_thing;
