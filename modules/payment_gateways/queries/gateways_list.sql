-- Lista de pasarelas del hub. Runtime inyecta :hub_id. Portado de PaymentGatewayService.list_gateways.
-- Nota: el enmascarado de secretos de `config` (mask_config) lo hace el handler WASM al serializar; aquí
-- se devuelve el JSON crudo y el WC NUNCA debe pintar `config` sin pasar por el handler. Ver WASM-TODO.md.
SELECT id, code, name, provider, is_active, is_test_mode,
       supports_refunds, supported_currencies, created_at
FROM payment_gateways_gateway
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY name ASC;
