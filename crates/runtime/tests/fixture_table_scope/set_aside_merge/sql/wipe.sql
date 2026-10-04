MERGE INTO _deprecated_set_aside_merge_request r USING (SELECT :hub_id AS hub_id) s ON r.hub_id = s.hub_id
WHEN MATCHED THEN UPDATE SET data = NULL;
