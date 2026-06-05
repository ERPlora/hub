-- Lotes de pago del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de CommissionsService.list_payouts. Filtros: :status ('' = todos),
-- :staff_id ('' = todos). Orden por fin de periodo descendente.
SELECT id, reference, staff_id, staff_name, period_start, period_end,
       gross_amount, tax_amount, adjustments_amount, net_amount,
       transaction_count, status, payment_method, payment_reference,
       approved_at, paid_at, notes
FROM commissions_payout
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status   = '' OR status   = :status)
  AND (:staff_id = '' OR staff_id = :staff_id)
ORDER BY period_end DESC, created_at DESC
LIMIT :limit;
