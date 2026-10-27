# VeriFactu (`verifactu`)

El final de la cadena fiscal: cada factura o tique que emite Facturación se convierte en su **registro de
facturación** para la AEAT, encadenado al anterior por su huella SHA-256, con el QR que coteja el cliente, validado
contra los esquemas oficiales y enviado en orden por la pasarela de ERPlora (`fiscal_gateway/` del SaaS), respetando
la espera que pide la AEAT. Lo que no puede salir espera en la cola y sale solo; un rechazo se subsana con un
registro nuevo. Solo para negocios de España (Canarias, Ceuta y Melilla incluidas); fuera, se porta como apagada.

- **Estado**: completa (2026-10-27): 32 de los 35 flujos `VERIFACTU-F01` … `F35` están `hecho`; F07, F23 y F33,
  `descartado` con su motivo (y las claves `G` del registro de migración, también `descartado`).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Configuración y vía** (F01–F06, F08–F12, F34): dos vías de envío, las dos por la pasarela del SaaS: ERPlora
  remite con su sello y el otorgamiento de representación (Anexo I del Convenio 17) que se firma y se sube aquí y
  revisa el staff en el SaaS, o el negocio remite con su certificado propio, subido aquí y guardado cifrado (Fernet,
  `FISCAL_CERTIFICATE_KEY`) en la BD del hub. Empieza en pruebas; pasar a producción exige despliegue `prod`,
  `VERIFACTU_PRODUCTION_ENABLED`, la vía lista y la cuenta activa, en todos los planes. Prueba de conexión sin
  presentar nada, factura de prueba y declaración responsable.
- **Registrar** (F13, F14): Facturación pide el registro de alta dentro de su propia emisión (la reacción a
  `invoice.invoice.issued` queda de respaldo); si no cuadra o el XML no pasa el esquema, la emisión entera se
  deshace. En producción sin vía, no se sella, ni se numera, ni se cobra.
- **Enviar y la cola** (F15, F20–F22, F25, F35): la tarea de cada minuto agrupa hasta 1.000 registros por envío,
  respeta `TiempoEsperaEnvio`, reintenta lo pasajero con incidencia y nunca da por aceptado nada sin respuesta;
  «Procesar cola», «Reintentar», «Enviar ahora» y «Preguntar a la AEAT».
- **Consultar y corregir** (F16–F19, F24, F30, F31): lista y ficha con su QR, XML y por qué espera; subsanación y
  anulación como registros nuevos; QR y estado fiscal para el tique y la factura; eventos de auditoría y cuatro
  paneles del Inicio.
- **La cadena** (F26–F29): verificarla, consultar lo que tiene la AEAT, recuperarla desde la AEAT tras restaurar
  una copia y continuar la de otra aplicación.
- **Apagar** (F32): la plataforma no la deja apagar mientras haya registros que la AEAT aún no tiene.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:shield-checkmark-outline` (el escudo del módulo actual; también en Recuperación, el paso y el panel «Pendientes VeriFactu» del Inicio), categoría `sales`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | `["invoice"]`: sin facturas no hay nada que registrar; Facturación no se apaga mientras VeriFactu esté encendida |
| Usa de otras apps | la factura emitida de Facturación (su fila, por id) y su `invoice.invoice.create` para la factura de prueba; el país del negocio (`base.business.get`) y si es una demo (`base.operations.is_demo_hub`), de `base`; el estado del otorgamiento y de la cuenta llega en la foto del SaaS (`verifactu.config.sync`) |
| Quién la lee | Facturación (`verifactu.record.create` dentro de su emisión), Ventas, Facturación e Impresión (`verifactu.record.by_invoice`), la plataforma (`can_disable`) y Automatizaciones (la tarjeta de FLOW-F04 ante un rechazo) |
| Pantallas | `/verifactu/records` (y la ficha `/verifactu/records/<id>`), `/verifactu/contingency`, `/verifactu/events`, `/verifactu/recovery`, `/verifactu/config` y `/verifactu/settings` |
| Inicio | el paso «Configura VeriFactu» (`verifactu.sending_route`, `required=True`; legal en producción por `base`) y cuatro paneles: «Pendientes VeriFactu» (de serie), «Cola de contingencia», «Registros por estado» y «Eventos AEAT recientes» |
| Operaciones | 14 consultas (`queries.py`) y 21 acciones (`services.py`), todas con `ai=`; 33 rutas en `/api/verifactu/…` (`verifactu.config.sync` y `verifactu.config.follow_deployment` no tienen ruta: solo el sistema) |
| Eventos | 12, `verifactu.record.{created,transmitted,rejected,accepted_with_errors,reconciled}`, `verifactu.contingency.{processed,retried}`, `verifactu.chain.{validated,recovered}`, `verifactu.aeat.queried`, `verifactu.diagnostic.run` y `verifactu.config.changed` (`events.py`); reacciona a `invoice.invoice.issued` |
| Tarea programada | `process_queue` (`verifactu.contingency.process`, cada minuto, `catch_up: collapse`) |
| Migraciones | `0001_initial`, `0002_own_certificate`, `0003_live_paid` (columna sin uso, a la espera de su contracción), `0004_multiple_taxpayers_always`, `0005_config_hub_id` |
| Admin | Django admin en `hubs.erplora.com` sin CRUD libre sobre sus siete modelos (PLAN §28): lo registrado, en solo lectura; lo no registrado, con acciones de soporte que son operaciones («Reenviar a la AEAT», «Reprogramar», «Consultar a la AEAT», «Subsanar el rechazo»); la vía, por `verifactu.config.update` |
| Pasarela | `VERIFACTU_GATEWAY_URL` (la del SaaS, firmada con HMAC); sin ella los registros esperan en la cola con su motivo |

Las decisiones de diseño (la cola son los propios registros, un SOAP Fault no rechaza registros, un rechazo deshace
la emisión, sin reenganche automático, solo España…) y las contradicciones abiertas están en «Para quien lo
mantiene» del WORKBOOK; las de la migración, en la ronda 2026-10-27 (CLOSE-VERIFACTU) de `PLAN-HUB.md` (raíz de
erplora-next). El modelo fiscal de fondo vive en PLAN §25 y §28.

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/verifactu
pnpm test apps/verifactu
CI=1 pnpm e2e tests/e2e/verifactu-flows.spec.ts tests/e2e/verifactu-config.spec.ts tests/e2e/verifactu-records.spec.ts
```

- La huella y el QR se prueban con los tres casos oficiales de la AEAT (`test_chain.py`); el XML, contra los
  esquemas reales (`test_xsd.py`, `test_envelope.py`); la respuesta de la AEAT, con las capturas del motor viejo
  (`tests/fixtures/`, `test_aeat.py`).
- `test_integration_invoice.py` va contra Facturación real; `test_relay.py`, por el tick real del relay del outbox;
  `test_concurrency.py`, con hilos (un registro y un número por factura). Los de tenencia van con dos hubs.
- Nunca hay red real de la AEAT ni certificados reales: la pasarela se sustituye en los tests y en la e2e no hay
  pasarela (lo que iría a la AEAT dice por qué no pudo). Solo entorno de pruebas (working-rules §15).
- Además de las tres e2e de la app: `fix-verifactu-setup-hooks`, `fix-hub-home-verifactu-legal-level-in-production`,
  `fix-hub-verifactu-retire-live-paid` y `fix-hub-verifactu-on-for-a-business-outside-spain`.

## Qué queda fuera

- Lo que no hace a propósito (emitir facturas, calcular impuestos, guardar el sello de ERPlora, presentar por su
  cuenta, la modalidad NO VERI\*FACTU, el cese): «Lo que NO hace» del WORKBOOK.
- Lo aplazado del bloque fiscal y lo que sigue en la cola fuera de su carril (el paso del Inicio y «Activar» fuera de
  España, la autorización en pruebas, la contracción de `live_paid`): «Qué queda fuera» del WORKBOOK.
- Los iconos y las piezas compartidas de [`UI-REQUESTS.md`](UI-REQUESTS.md).
