-- Alta de una entrada de auditoría del KDS. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de kitchen.models.create_kitchen_log; lo disparan los
-- listeners de eventos kitchen_orders.order_{fired,ready,served,cancelled} (events.listen)
-- y también puede invocarse directamente. order_item_id/station_id/performed_by_id opcionales.
INSERT INTO kitchen_order_log
  (id, hub_id, order_id, order_item_id, station_id, action, performed_by_id, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :order_id, :order_item_id, :station_id, :action, :performed_by_id, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
