-- Tarifas de envío del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de CarriersService.list_rates. La vigencia por fecha (is_active_on / active_on) y
-- el quote_shipment (filtro por bracket de peso) los aplica el SDK/WASM — ver WASM-TODO.
-- Binds: :carrier_id, :origin_country, :destination_country ('' = sin filtro).
SELECT id, carrier_id, service_type, origin_country, destination_country,
       weight_from_kg, weight_to_kg, price, currency,
       delivery_days_min, delivery_days_max, valid_from, valid_until
FROM carriers_shipping_rate
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:carrier_id = '' OR carrier_id = :carrier_id)
  AND (:origin_country = '' OR origin_country = :origin_country)
  AND (:destination_country = '' OR destination_country = :destination_country)
ORDER BY price ASC;
