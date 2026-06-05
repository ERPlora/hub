-- Alta de gasto en estado draft. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ExpenseService.create_expense. La validación de que category_id existe en el
-- hub la garantiza la FK + la UI (preselecciona de la lista de categorías).
-- :expense_date debe venir resuelta (ISO YYYY-MM-DD); el default a hoy lo aplica el SDK/UI.
INSERT INTO expenses_expense
  (id, hub_id, category_id, description, amount, expense_date, supplier_name,
   status, notes, rejection_reason,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :category_id, :description, :amount, :expense_date, :supplier_name,
   'draft', :notes, '',
   0, :current_user_id, :current_user_id, :now, :now);
