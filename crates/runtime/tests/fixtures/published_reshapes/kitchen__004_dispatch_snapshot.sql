-- Pieza 0 del envío incremental: cantidades fraccionables + el destino como HECHO HISTÓRICO.
--
-- 1) CANTIDAD FRACCIONABLE. `sales_order_item.quantity` es REAL ("cantidad fraccionable"): medio
--    kilo de gambas o media ración son cantidades reales de un bar. Cocina la guardaba en INTEGER
--    y el handler la convertía con `as_i64` → `0.5 as i64` = 0: al cocinero le llegaba
--    «0 × Gambas». Aquí, a diferencia de SQLite, la columna INTEGER lo rompe de verdad.
--    Es además PREREQUISITO del envío incremental: el delta es `quantity - dispatched_quantity`,
--    así que si cocina trunca, `sales` cree que comunicó 0.5 y cocina recibió 0 → esa línea se
--    reenviaría en cada disparo, para siempre.
--
-- 2) EL DESTINO ES HISTORIA, NO CONFIGURACIÓN. `order_items.sql` resolvía destino/rol/nombre con
--    un JOIN VIVO a `kitchen_station`. Consecuencia: si mañana la plancha pasa a solo-pantalla, la
--    ronda que salió AYER por papel se reimprime por pantalla — y, peor, el vale de anulación de
--    «quita las croquetas» llegaría a una estación que no las está cocinando. Se congela al
--    insertar: la configuración de hoy vale para los envíos NUEVOS, nunca para reconstruir los
--    pasados.
--
-- 3) TRAZA HASTA LA LÍNEA DE PEDIDO. Sin `sales_order_item_id` no se puede responder «¿de qué
--    línea salió esto?», que es lo que necesita la anulación para repartir cantidades por LIFO
--    entre las estaciones que recibieron cada ronda.
--
-- 4) IDEMPOTENCIA DEL OUTBOX. Si el outbox reentrega el mismo dispatch, el índice único sobre
--    `sales_dispatch_item_id` impide que cocina duplique la ronda. Hoy no hay quien lo escriba
--    (el dispatch llega en la pieza 1): la columna queda NULL y el índice no guarda nada todavía
--    — los NULL no colisionan entre sí.
ALTER TABLE kitchen_order_item ADD COLUMN IF NOT EXISTS sales_order_item_id    TEXT;
ALTER TABLE kitchen_order_item ADD COLUMN IF NOT EXISTS sales_dispatch_item_id TEXT;
ALTER TABLE kitchen_order_item ADD COLUMN IF NOT EXISTS station_name TEXT NOT NULL DEFAULT '';
ALTER TABLE kitchen_order_item ADD COLUMN IF NOT EXISTS destination  TEXT NOT NULL DEFAULT 'both';
ALTER TABLE kitchen_order_item ADD COLUMN IF NOT EXISTS printer_role TEXT NOT NULL DEFAULT 'kitchen';

-- Postgres SÍ trunca: la columna tiene que cambiar de tipo, no basta con arreglar el handler.
ALTER TABLE kitchen_order_item ALTER COLUMN quantity TYPE REAL;
ALTER TABLE kitchen_order_item ALTER COLUMN quantity SET DEFAULT 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_kitchen_item_dispatch_item
    ON kitchen_order_item (hub_id, sales_dispatch_item_id)
    WHERE sales_dispatch_item_id IS NOT NULL AND is_deleted = 0;
CREATE INDEX IF NOT EXISTS ix_kitchen_item_sales_line
    ON kitchen_order_item (hub_id, sales_order_item_id);
