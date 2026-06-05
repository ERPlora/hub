-- Alta de suscripción a entregas recurrentes de un informe.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ReportService.subscribe. La validación de frequency/delivery_method (enums) y la
-- existencia del informe la cubren el schema y el runtime (FK report_id).
INSERT INTO reports_subscription
  (id, hub_id, report_id, subscriber_ref, frequency, delivery_method, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :report_id, :subscriber_ref, :frequency, :delivery_method, 1,
   0, :current_user_id, :current_user_id, :now, :now);
