-- Transacciones de comisión del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de CommissionsService.get_summary + routes.transaction_list. Filtros opcionales:
--   :status     ('' = todas)
--   :staff_id   ('' = todos)
--   :date_from / :date_to  ('' = sin límite, formato ISO YYYY-MM-DD)
SELECT id, staff_id, staff_name, sale_id, sale_reference, appointment_id,
       sale_amount, commission_rate, commission_amount, tax_amount, net_commission,
       rule_id, status, payout_id, transaction_date, approved_at, description, notes
FROM commissions_transaction
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status    = '' OR status   = :status)
  AND (:staff_id  = '' OR staff_id = :staff_id)
  AND (:date_from = '' OR transaction_date >= :date_from)
  AND (:date_to   = '' OR transaction_date <= :date_to)
ORDER BY transaction_date DESC, created_at DESC
LIMIT :limit;
