-- Conceptos de nómina activos del hub. Runtime inyecta :hub_id.
-- Portado de ConceptService.list_concepts. :concept_type vacío = sin filtro de tipo.
SELECT id, name, type, is_percentage, amount, percentage, is_taxable, sort_order
FROM payroll_concept
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
  AND (:concept_type = '' OR type = :concept_type)
ORDER BY sort_order ASC, name ASC;
