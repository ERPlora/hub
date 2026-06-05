-- Alta de lista de precios. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PricingService.create_price_list.
-- NOTA: la invariante "una sola lista default por hub" (flip del default previo) NO se
-- modela aquí en Tier 0 — va al handler WASM `create_price_list` (ver WASM-TODO.md §1),
-- que invoca `pricing._unset_default` antes de este INSERT dentro de la misma transacción.
-- Este INSERT respeta is_default tal cual llega.
INSERT INTO pricing_price_list
  (id, hub_id, code, name, currency, is_default, is_active, valid_from, valid_until, segment,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :currency, :is_default, 1, :valid_from, :valid_until, :segment,
   0, :current_user_id, :current_user_id, :now, :now);
