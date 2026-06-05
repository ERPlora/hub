-- Transición de estado de un pedido (tabla PROPIA orders_order).
-- Reemplaza al antiguo sale_set_status.sql, que hacía UPDATE sobre sales_sale
-- (tabla privada de `sales`) — PROHIBIDO por el contrato cross-module §2.3.
-- Usado por orders.confirm (draft→pending) y orders.cancel (→voided).
-- La UI deriva :new_status del actionId (confirm/cancel) y envía :order_id.
-- El runtime inyecta :current_user_id y :now.
-- NOTA: la validación de la transición permitida ("solo draft puede confirmarse",
-- "no cancelar pedidos completados/anulados"), la escritura de la nota status_change
-- (lee el estado anterior + compone el texto) y el efecto sobre la venta vinculada
-- (sale_id) son lógica de dominio → ver WASM-TODO.md.
UPDATE orders_order SET
  status     = :new_status,
  updated_by = :current_user_id,
  updated_at = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
