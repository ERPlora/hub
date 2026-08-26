UPDATE gate_legacy_single_t SET state = 'resolved'
WHERE hub_id = :hub_id AND id = :id AND state = 'open'
