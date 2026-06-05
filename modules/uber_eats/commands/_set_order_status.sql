-- Transición de estado de un pedido, invocada por los handlers WASM update_order_status /
-- cancel_order tras validar las guardas (cancelled-locked, delivered-locked). El handler
-- aporta :id y :status (ya validado). Runtime inyecta :hub_id, :current_user_id, :now.
-- :customer_notes lo recompone el handler (p.ej. añade el rastro "[CANCELLED] reason").
UPDATE uber_eats_order
SET status        = :status,
    customer_notes = :customer_notes,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
