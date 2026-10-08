-- Stand-in of a fiscal provider's ingest: records that a fiscal event reached it.
INSERT INTO fprov2612_records (id, hub_id, created_at) VALUES (:new_id, :hub_id, :now);
