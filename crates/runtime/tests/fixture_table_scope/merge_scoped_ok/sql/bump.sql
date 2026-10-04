-- Upserts its own table with all three MERGE actions; none of them is a statement of its own.
MERGE INTO merge_scoped_ok_item i
USING (SELECT CAST(:hub_id AS TEXT) AS hub_id, CAST(:item_id AS TEXT) AS id) s
ON i.hub_id = s.hub_id AND i.id = s.id
WHEN MATCHED AND i.n >= 2 THEN DELETE
WHEN MATCHED THEN UPDATE SET n = i.n + 1
WHEN NOT MATCHED THEN INSERT (hub_id, id, n) VALUES (s.hub_id, s.id, 1);
