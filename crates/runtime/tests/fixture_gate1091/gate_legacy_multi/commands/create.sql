INSERT INTO gate_legacy_multi_t (id, hub_id)
SELECT :new_id, :hub_id WHERE CAST(:window_ok AS TEXT) = '1'
