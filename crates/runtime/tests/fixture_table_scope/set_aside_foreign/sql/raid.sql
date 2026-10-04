-- Another module's set-aside table is still another module's data.
UPDATE _deprecated_inventory_product SET price = 0 WHERE hub_id = :hub_id;
