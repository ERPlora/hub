-- Registra una compra: incrementa stats y transiciona el lifecycle (CASE, fiel al
-- modelo record_purchase). Lo invoca el listener de sale.completed; el payload del
-- evento aporta :total y :customer_id. Si customer_id es NULL (venta anónima), el
-- WHERE no casa ninguna fila → no-op seguro. Runtime inyecta :hub_id, :now.
UPDATE customers_customer SET
  total_purchases = total_purchases + 1,
  total_spent = total_spent + :total,
  last_purchase_date = :now,
  lifecycle_stage = CASE
    WHEN lifecycle_stage IN ('lead', 'prospect') THEN 'first_purchase'
    WHEN lifecycle_stage IN ('first_purchase', 'at_risk', 'dormant') THEN 'active'
    ELSE lifecycle_stage
  END,
  updated_at = :now
WHERE id = :customer_id AND hub_id = :hub_id AND is_deleted = 0;
