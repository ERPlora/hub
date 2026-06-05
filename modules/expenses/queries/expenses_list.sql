-- Gastos del hub con filtros opcionales por estado y/o categoría. Runtime inyecta :hub_id.
-- Portado de ExpenseService.list_expenses (orden por fecha descendente).
-- Binds :status y :category_id deben pasarse: '' = sin filtro.
SELECT id, category_id, description, amount, expense_date, supplier_name,
       status, notes, approved_by, approved_at, rejection_reason
FROM expenses_expense
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status      = '' OR status      = :status)
  AND (:category_id = '' OR category_id = :category_id)
ORDER BY expense_date DESC;
