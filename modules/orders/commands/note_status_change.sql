-- Registra una entrada de bitácora tipo 'status_change' al confirmar/cancelar un pedido.
-- Portado de OrderService._record_status_change. Referencia el pedido por order_id.
-- NOTA: este comando declarativo asume que :from_status/:to_status/:content ya vienen
-- resueltos (el estado anterior se lee del pedido y el texto se compone). En el flujo
-- Tier 0 la UI solo dispone de :order_id + :new_status, así que la composición de esta
-- nota es lógica de transición → la produce el handler WASM (ver WASM-TODO.md), que
-- invoca este comando interno con los binds completos.
-- Binds: :new_id, :order_id, :content, :from_status, :to_status,
--        :author_id, :author_name, :current_user_id, :now (+ :hub_id inyectado).
INSERT INTO orders_note
  (id, hub_id, order_id, note_type, content, author_id, author_name,
   from_status, to_status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :order_id, 'status_change', :content, :author_id, :author_name,
   :from_status, :to_status,
   0, :current_user_id, :current_user_id, :now, :now);
