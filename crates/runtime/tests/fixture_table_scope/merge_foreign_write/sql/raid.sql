MERGE INTO inventory_product p USING (SELECT :hub_id AS hub_id) s ON p.hub_id = s.hub_id
WHEN MATCHED THEN DELETE;
