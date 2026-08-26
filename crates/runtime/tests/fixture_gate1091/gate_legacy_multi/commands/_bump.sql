INSERT INTO gate_legacy_multi_counter (hub_id, seq) VALUES (:hub_id, 1)
ON CONFLICT (hub_id) DO UPDATE SET seq = gate_legacy_multi_counter.seq + 1
