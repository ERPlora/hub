-- Alta de una nota libre en la bitácora de un pedido (note/customer_contact/internal).
-- Referencia el pedido por order_id (tabla propia orders_order).
-- Binds: :new_id, :order_id, :note_type, :content, :author_id, :author_name,
--        :current_user_id, :now (+ :hub_id inyectado).
INSERT INTO orders_note
  (id, hub_id, order_id, note_type, content, author_id, author_name,
   from_status, to_status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :order_id, :note_type, :content, :author_id, :author_name,
   '', '',
   0, :current_user_id, :current_user_id, :now, :now);
