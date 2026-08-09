UPDATE inventory_product SET stock = stock - :qty, updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id;
