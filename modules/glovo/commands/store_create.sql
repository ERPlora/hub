-- Alta de tienda Glovo. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de GlovoService.create_store. La unicidad de (hub_id, store_id) la garantiza
-- el índice ix_glovo_store_hub_store_id; el chequeo previo de duplicado va a runtime.
INSERT INTO glovo_store
  (id, hub_id, store_id, name, country, city, glovo_status, is_active,
   last_sync_at, settings, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :store_id, :name, :country, :city, 'offline', 1,
   NULL, '{}', 0, :current_user_id, :current_user_id, :now, :now);
