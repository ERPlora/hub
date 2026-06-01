-- Nota de cliente. Portado de ActivityService.add_note (la actividad 'note' la añade el handler).
INSERT INTO customers_customernote
  (id, hub_id, customer_id, content, author_id, author_name,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :customer_id, :content, :current_user_id, :author_name,
   0, :current_user_id, :current_user_id, :now, :now);
