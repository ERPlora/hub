-- Detalle de una orden de fabricación. Runtime inyecta :hub_id.
-- Portado de ManufacturingOrderService.get_mo (cabecera; las líneas de material
-- se obtienen aparte con manufacturing_orders.materials.list).
SELECT id, mo_number, product_ref, quantity_planned, quantity_produced,
       scheduled_date, due_date, status, priority, work_center_ref, notes,
       started_at, completed_at, created_at
FROM manufacturing_orders_order
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :mo_id;
