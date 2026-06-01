-- Descuento de stock de UN producto por :qty, sin bajar de 0 (MAX(0, stock-qty)).
-- Lo invoca el listener de sale.completed (una baja por producto). Portado de
-- events._on_sale_completed (rama allow_negative=false: greatest(0, stock - qty)).
-- Los servicios nunca descuentan stock de productos de tipo 'service'.
UPDATE inventory_product
SET stock = MAX(0, stock - :qty),
    updated_at = :now
WHERE id = :product_id AND hub_id = :hub_id AND is_deleted = 0 AND product_type != 'service';
