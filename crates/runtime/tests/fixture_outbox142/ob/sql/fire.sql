-- Sin efectos de negocio: el command existe SOLO para emitir `ob.e` (síntoma a)
-- y dejarlo en el outbox dentro de la misma transacción. Un INSERT descartable
-- (`SELECT`) evita depender de tablas de negocio.
SELECT 1;
