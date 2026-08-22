-- hub#1092 fixture: a NARROW numeric column (`FLOAT4`, i.e. `real`) with a range CHECK.
-- The DDL shim does not rewrite `FLOAT4` (only the portable tokens TEXT/INTEGER/REAL/BLOB),
-- so this lands as a true 4-byte float — the loud variant of the frozen-plan misread.
CREATE TABLE ptype_rule (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  rate FLOAT4 NOT NULL CHECK (rate >= 0 AND rate <= 100)
);
