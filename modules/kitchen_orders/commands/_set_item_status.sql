-- Fija el estado y marcas de tiempo de UNA línea. Helper invocado por el handler WASM
-- (update_order_status — cascada a las líneas de la comanda). Runtime inyecta :hub_id,
-- :current_user_id, :now. fired_at/started_at/completed_at = NULL los gestiona el handler.
UPDATE kitchen_orders_order_item
SET status       = :status,
    fired_at     = COALESCE(:fired_at, fired_at),
    started_at   = COALESCE(:started_at, started_at),
    completed_at = :completed_at,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :item_id AND hub_id = :hub_id AND is_deleted = 0;
