-- Añade una entrada al timeline del cliente. Portado de log_customer_activity / ActivityService.add_activity.
-- Lo usan listeners (sale.completed, etc.) y el handler de notas. Runtime inyecta :new_id, :hub_id, :now, :current_user_id.
INSERT INTO customers_customeractivity
  (id, hub_id, customer_id, activity_type, title, description, extra_metadata,
   related_object_id, related_object_type, performed_by,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :customer_id, :activity_type, :title, :description, :extra_metadata,
   :related_object_id, :related_object_type, :current_user_id,
   0, :current_user_id, :current_user_id, :now, :now);
