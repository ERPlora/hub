-- Alta de ajuste manual de comisión. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CommissionAdjustmentCreate / routes.adjustment_add. staff_name es snapshot
-- (se resuelve vía query pública de staff antes de llamar; este módulo no toca staff_member).
INSERT INTO commissions_adjustment
  (id, hub_id, staff_id, staff_name, adjustment_type, amount, reason, payout_id,
   adjustment_date, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :staff_id, :staff_name, :adjustment_type, :amount, :reason, :payout_id,
   :adjustment_date, 0, :current_user_id, :current_user_id, :now, :now);
