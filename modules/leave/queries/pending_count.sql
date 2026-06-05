-- Recuento de solicitudes pendientes del hub. Runtime inyecta :hub_id.
-- Portado de LeaveService.get_pending_count.
SELECT COUNT(*) AS pending_count
FROM leave_request
WHERE hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
