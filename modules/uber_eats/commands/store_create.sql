-- Alta de una tienda Uber Eats para el hub. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de UberEatsService.create_store.
-- La unicidad (hub_id, store_id) la garantiza el índice ix_ue_store_hub_sid;
-- el error "duplicate_store" lo materializa el runtime al violar el índice.
INSERT INTO uber_eats_store
  (id, hub_id, store_id, name, status, country, currency, is_active, last_sync_at, settings,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :store_id, :name, 'active', :country, :currency, 1, NULL, NULL,
   0, :current_user_id, :current_user_id, :now, :now);
