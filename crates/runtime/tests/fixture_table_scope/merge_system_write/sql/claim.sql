MERGE INTO ONLY _hub_fiscal_profile f USING (SELECT :hub_id AS hub_id) s ON f.hub_id = s.hub_id
WHEN NOT MATCHED THEN INSERT (hub_id, status) VALUES (s.hub_id, 'ACTIVE');
