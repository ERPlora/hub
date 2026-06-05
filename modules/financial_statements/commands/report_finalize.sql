-- Finaliza un informe (draft → final). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de FinancialReportService.finalize_report. El guard de estado (solo desde 'draft')
-- se aplica con el WHERE status='draft': si no afecta filas, el runtime devuelve invalid_state.
UPDATE financial_statements_generated
SET status     = 'final',
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :report_id AND status = 'draft';
