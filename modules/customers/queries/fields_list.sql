-- Campos personalizados definidos en el hub. Portado de FieldService.list_fields.
SELECT id, name, field_type, options, is_required, sort_order, is_active
FROM customers_customerfield
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY sort_order ASC, name ASC;
