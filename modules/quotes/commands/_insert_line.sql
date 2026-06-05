-- Alta de una línea de cotización. Comando interno invocado por el handler WASM
-- (create_quote / update_quote_lines) una vez calculado line_total. Runtime inyecta
-- :hub_id, :current_user_id, :now; el WASM provee :new_id y :line_total ya calculado.
INSERT INTO quotes_quote_line
  (id, hub_id, quote_id, description, quantity, unit_price, discount_pct, tax_rate, line_total,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :quote_id, :description, :quantity, :unit_price, :discount_pct, :tax_rate, :line_total,
   0, :current_user_id, :current_user_id, :now, :now);
