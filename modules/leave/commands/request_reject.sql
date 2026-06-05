-- Rechazo de una solicitud pendiente. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de LeaveService.reject_request / LeaveRequest.reject. Guard status='pending' en WHERE.
UPDATE leave_request
SET status           = 'rejected',
    rejection_reason = :reason,
    updated_by       = :current_user_id,
    updated_at       = :now
WHERE id = :request_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
