-- Lista de entradas de amortización del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de routes.list_depreciations. Binds opcionales: :asset_id ('' = todos),
-- :posted (-1 = sin filtro, 0 = no posteadas, 1 = posteadas). Orden por periodo descendente.
SELECT id, asset_id, period_start, period_end, depreciation_amount,
       accumulated_after, book_value_after, posted, posted_at
FROM fixed_assets_depreciation
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:asset_id = '' OR asset_id = :asset_id)
  AND (:posted   = -1 OR posted   = :posted)
ORDER BY period_start DESC;
