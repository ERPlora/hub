-- Detalle completo de un gasto por id. Runtime inyecta :hub_id.
-- Portado de ExpenseService.get_expense.
SELECT id, category_id, description, amount, expense_date, supplier_name,
       status, notes, approved_by, approved_at, rejection_reason
FROM expenses_expense
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :expense_id;
