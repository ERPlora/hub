-- Fija el estado de un lead + el timestamp de hito y notas opcionales. Comando INTERNO
-- invocado por el handler WASM tras validar la transición (mark_contacted, qualify_lead,
-- unqualify_lead, convert_lead, mark_lost). El WASM ya ha calculado el nuevo :status,
-- los timestamps de hito (:contacted_at/:qualified_at/:converted_at, NULL si no aplica),
-- :estimated_value y :notes (con el rastro [UNQUALIFIED]/[LOST] añadido). Runtime inyecta scope.
UPDATE leads_lead
SET status          = :status,
    estimated_value = :estimated_value,
    notes           = :notes,
    contacted_at    = :contacted_at,
    qualified_at    = :qualified_at,
    converted_at    = :converted_at,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :lead_id AND hub_id = :hub_id AND is_deleted = 0;
