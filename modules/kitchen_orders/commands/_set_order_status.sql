-- Fija el estado y marcas de tiempo de una comanda. Helper invocado por el handler WASM
-- (update_order_status). Runtime inyecta :hub_id, :current_user_id, :now.
-- El handler decide qué marcas pasar (NULL = no tocar) según la transición.
UPDATE kitchen_orders_order
SET status     = :status,
    fired_at   = COALESCE(:fired_at, fired_at),
    ready_at   = :ready_at,
    served_at  = :served_at,
    notes      = COALESCE(:notes, notes),
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
