-- Alta de proveedor. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de PurchaseOrderService.create_supplier.
INSERT INTO purchase_orders_supplier
  (id, hub_id, name, tax_id, email, phone, address, notes, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :tax_id, :email, :phone, :address, :notes, 1,
   0, :current_user_id, :current_user_id, :now, :now);
