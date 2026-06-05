-- Alta de un objetivo SLA ligado a un bucket de prioridad. Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now. Portado de TicketService.create_sla.
-- La validación de priority (enum) y horas > 0 va en el JSON Schema del command.
INSERT INTO tickets_sla
  (id, hub_id, name, description, priority,
   response_time_hours, resolution_time_hours, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :priority,
   :response_time_hours, :resolution_time_hours, 1,
   0, :current_user_id, :current_user_id, :now, :now);
