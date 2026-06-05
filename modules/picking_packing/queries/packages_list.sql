-- Listado de paquetes con filtro opcional de estado. Runtime inyecta :hub_id.
-- Portado de PickPackService.list_packages. Bind :status ('' = sin filtro).
SELECT id, package_number, pick_list_ref, weight_kg, dimensions,
       tracking_number, carrier, status, packed_at, packed_by_ref, created_at
FROM picking_packing_package
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
