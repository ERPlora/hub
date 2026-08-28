-- Kernel fixture · migration 002 (contract) — the legacy table is retired.
-- The author writes `DROP`; the kernel translates it into a rename, so the rows are still there
-- and the retirement is reversible. This header comment is deliberate: it is the shape hub#1137
-- proved could slip a real, irreversible DROP past the guard.
DROP TABLE IF EXISTS kfx_legacy;
