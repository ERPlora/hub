# `fixture_wa_quota` — el contrato de `whatsapp_inbox._quota.set` (hub#1089)

Espejo **mínimo** del módulo real `ERPlora/whatsapp_inbox` (v2.1.29), reducido a lo único que el
hub tiene que saber para sincronizar la cuota del plan:

- la tabla singleton `whatsapp_inbox_settings` con su columna `free_tier_monthly_limit` y su
  índice único por `hub_id` (el `ON CONFLICT` del command apunta a él);
- el command **interno** `whatsapp_inbox._quota.set`, con el mismo `internal: true`, el mismo
  permiso y el mismo `INSERT … ON CONFLICT` que el real (`commands/quota_set.sql` del módulo):
  siembra la fila si el comerciante nunca abrió los ajustes y, en conflicto, mueve **solo** el
  medidor y el sello de auditoría.

Está aquí y no se instala el módulo real porque el módulo es **otro repo git** y el hub no lo
contiene: los e2e del runtime trabajan igual, con fixtures que reproducen el contrato publicado.
Lo que este fixture prueba es lo que es del hub — que la sincronización llama al command por la
puerta INTERNA y con el número correcto —, no el SQL del módulo, que tiene sus propios tests.
