-- Alta de categoría de auditoría. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de AuditService.create_category (code único por hub — lo garantiza el índice).
INSERT INTO audit_log_category
  (id, hub_id, code, name, severity_default, retention_days,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :severity_default, :retention_days,
   0, :current_user_id, :current_user_id, :now, :now);
