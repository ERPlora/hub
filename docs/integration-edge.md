# Borde de integración del Hub (ADR-0049)

Estado de esta entrega: fases 1–3 ejecutables en Hub Cloud; fases 4–5 auditadas abajo.

## Decisiones cerradas

- Entrada: API key opaca `erpl_live_…` por `Authorization: Bearer`, siempre sobre TLS. Reutilizar
  ADR-0057 evita dos registros de credenciales incompatibles. El secreto se guarda con Argon2id,
  solo se revela al crear/rotar, y revocar es un kill switch inmediato.
- Alcance: Hub Cloud, online y PostgreSQL-only (ADR-0154). No se implementa pull para un producto
  Local/offline que ya no existe.
- Inyección: solo un command del módulo marcado `expose_api`; nunca un evento crudo. Se conserva el
  JSON Schema, permisos, transacción y Outbox del dispatcher.
- Salida: opt-in doble. El módulo declara `events.external`; el admin registra los eventos exactos
  de cada suscripción. El secreto `whsec_…` se cifra en reposo con `HUB_SECRETS_KEY`.
- Seguridad de destinos: HTTPS obligatorio, sin credenciales en URL, redirects desactivados y
  rechazo de localhost, dominios privados e IP privadas/reservadas después de resolver DNS. Solo
  `HUB_DEV_MODE` permite HTTP/loopback para pruebas locales.

## Entrada

`POST /webhook/{module}/{command}`

```http
Authorization: Bearer erpl_live_…
Content-Type: application/json

{
  "id": "stripe-event-or-order-id",
  "occurred_at": "2026-08-01T10:00:00Z",
  "payload": { "...": "schema del command" }
}
```

El `id` es obligatorio y se deduplica por `(hub_id, api_key_id, id)`. Un replay completo devuelve
el resultado original con `replay: true`; reutilizar el id con otro command o payload devuelve
`409`. El receipt de éxito se sella en la misma transacción que la mutación y el Outbox, por lo que
un crash no deja repetir el command. Un command fallido libera el receipt para un retry seguro. La
idempotencia de dominio continúa respaldada por claves como
`UNIQUE (hub_id, source_type, source_id)` en `invoice_invoice`.

Cada key lleva `rate_limit_per_minute` (default 60, rango 1–10.000). El contador es un UPSERT
atómico y durable en PostgreSQL, compartido por `/api/v1/**` y `/webhook/**`. Al excederlo responde
`429` y `Retry-After`.

El contrato del envelope está en `schemas/webhook-envelope.schema.json`; el OpenAPI dinámico añade
un path webhook por cada command expuesto.

## Salida

Gestión admin:

- `GET/POST /api/webhooks/subscriptions`
- `POST /api/webhooks/subscriptions/{id}/rotate`
- `DELETE /api/webhooks/subscriptions/{id}`

El Outbox entrega este cuerpo:

```json
{
  "id": "event-id-del-outbox",
  "type": "invoice.created",
  "created_at": "2026-08-01T10:00:00Z",
  "hub_id": "…",
  "data": {}
}
```

Headers: `X-ERPlora-Delivery`, `X-ERPlora-Event`, `X-ERPlora-Timestamp` y
`X-ERPlora-Signature: v1=<hex>`. La firma es HMAC-SHA256 de
`<timestamp>.<delivery-id>.<body-exacto>`. El receptor debe verificar firma, rechazar timestamps
antiguos y deduplicar por delivery id.

Cada destino usa un marcador `_event_delivery` independiente. Un destino fallido reintenta con el
backoff/dead-letter del Outbox sin repetir los destinos ya entregados. La semántica de red es
at-least-once: el receptor siempre debe deduplicar.

## Auditoría de fases del issue #64

- Fase 0: el flujo fiscal standalone ya tiene motor nativo y pruebas AEAT en el Hub; la aceptación
  manual contra AEAT testing sigue siendo una operación con certificado real, no código genérico.
- Fase 1: ya está en los repos canónicos de módulos: `invoice` tiene el índice único parcial
  `(hub_id, source_type, source_id)` y `verifactu` escucha `invoice.created` /
  `invoice.rectified` mediante `verifactu.records.ingest_invoice`.
- Fases 2–3: implementadas por este contrato.
- Fase 4: supersedida por ADR-0154. No hay Hub Local/offline; añadir SQS FIFO + pull recrearía un
  camino retirado. Cloud puede llamar directamente al endpoint online y recibir `429`/reintentar.
- Fase 5: no es un criterio decidido del borde. El issue mantiene abierta qué entra y en qué orden:
  reverse-charge/OSS, identidad fiscal internacional del cliente, multi-moneda, facturación
  recurrente y rol gestoría. Requiere una decisión fiscal/producto antes de mutar los módulos.
- Corte fiscal de Cloud: sigue siendo una decisión operativa explícita (fecha de corte, retención y
  cadena inicial) y no debe automatizarse desde este cambio de transporte.

Por esos dos últimos puntos, #64 es un epic y no se debe cerrar como completamente terminado con
esta entrega. #42 sí queda absorbido y técnicamente completado por las fases 2–3.
