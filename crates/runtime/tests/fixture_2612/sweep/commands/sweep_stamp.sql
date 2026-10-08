-- An unconditional sibling (a "last swept at" upsert): it ALWAYS affects one row, so it must
-- never be what decides whether the anchored statement changed something (hub#2612).
INSERT INTO w2612_sweeps (hub_id, last_sweep) VALUES (:hub_id, :now)
ON CONFLICT (hub_id) DO UPDATE SET last_sweep = EXCLUDED.last_sweep;
