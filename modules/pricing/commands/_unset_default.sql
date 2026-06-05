-- Helper interno: quita la marca is_default a la(s) lista(s) default actuales del hub.
-- Lo invoca el handler WASM create_price_list ANTES de insertar la nueva lista default,
-- para preservar la invariante "una sola lista default por hub". Portado del bloque
-- atomic() de PricingService.create_price_list (flip del default previo).
UPDATE pricing_price_list
SET is_default = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_default = 1 AND is_deleted = 0;
