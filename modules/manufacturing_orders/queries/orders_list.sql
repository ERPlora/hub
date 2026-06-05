-- Órdenes de fabricación del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ManufacturingOrderService.list_mos. Filtros opcionales por estado y
-- product_ref: '' = sin filtro. La validación de status válido la hace el SDK/runtime.
SELECT id, mo_number, product_ref, quantity_planned, quantity_produced,
       scheduled_date, due_date, status, priority, work_center_ref, notes,
       started_at, completed_at, created_at
FROM manufacturing_orders_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:product_ref = '' OR product_ref LIKE '%' || :product_ref || '%')
ORDER BY created_at DESC
LIMIT :limit;
