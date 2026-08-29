-- Kernel fixture · migration 001 (expand) — the module's own tables.
-- Every table carries `hub_id`: the row contract of the kernel, not a convention of this fixture.
CREATE TABLE IF NOT EXISTS kfx_item (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  name TEXT NOT NULL,
  created_by TEXT,
  created_at TEXT,
  updated_at TEXT,
  deleted_at TEXT
);

-- Retired by migration 002 in 1.1.0. It exists so the `contract` guard has something real to
-- retire, with a row in it that must survive the retirement.
CREATE TABLE IF NOT EXISTS kfx_legacy (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  note TEXT NOT NULL
);

-- What a listener wrote. The listener is the only thing that touches it.
CREATE TABLE IF NOT EXISTS kfx_log (
  event TEXT PRIMARY KEY,
  runs INTEGER NOT NULL DEFAULT 0
);
