-- ADR-0147 §2.1 — `pricing_price_list_item.min_quantity`/`max_quantity` a punto fijo ENTERO
-- escala 10⁶. Eran las ÚLTIMAS cantidades del proyecto que seguían en `REAL`: `sales` (014),
-- `kitchen` (005), `invoice` (004) y `cart_checkout` (003) ya habían migrado.
--
-- POR QUÉ AHORA, con el módulo sin consumidores. Comparar un `REAL` con un entero de escala 10⁶ no
-- da error: da un resultado creíble y equivocado por un factor de un millón — un bracket «de 10
-- unidades» al que nunca se llega, o un precio de mayorista aplicado a una unidad. Es la peor clase
-- de fallo, y el día que `pricing` estrene consumidor esta misma migración habría que hacerla sobre
-- tarifas REALES de clientes, con su backfill. Hoy las tablas están prácticamente vacías.
--
-- `USING ROUND(... * 1000000)` y no `(...::BIGINT * 1000000)`: la columna es REAL, así que castear a
-- entero PRIMERO truncaría el `0.5` de un bracket de medio kilo a `0` antes de escalarlo — que es
-- literalmente el defecto que ADR-0147 vino a cerrar. Se escala en coma flotante y se redondea al µ.
--
-- BIGINT y no INTEGER: 2^31 en µ son ~2.147 unidades lógicas, y un bracket de mayorista («a partir
-- de 5.000 ud») se sale. Es el mismo motivo que anotó `cart_checkout` en su 003.
--
-- `max_quantity` sigue admitiendo NULL: es «sin tope superior», no «cero».
ALTER TABLE pricing_price_list_item
  ALTER COLUMN min_quantity TYPE BIGINT USING ROUND(min_quantity * 1000000)::BIGINT;
ALTER TABLE pricing_price_list_item
  ALTER COLUMN min_quantity SET DEFAULT 1000000;
ALTER TABLE pricing_price_list_item
  ALTER COLUMN max_quantity TYPE BIGINT USING ROUND(max_quantity * 1000000)::BIGINT;
