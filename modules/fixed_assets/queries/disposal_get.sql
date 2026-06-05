-- Baja registrada para un activo concreto (0 o 1 fila). Runtime inyecta :hub_id.
-- Portado de FixedAssetService.get_asset (rama disposal).
SELECT id, asset_id, disposal_date, disposal_type, sale_price, gain_loss, notes
FROM fixed_assets_disposal
WHERE hub_id = :hub_id AND is_deleted = 0 AND asset_id = :asset_id
LIMIT 1;
