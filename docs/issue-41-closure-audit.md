# Auditoría de cierre de ERPlora/hub#41

Propuesta: cerrar como `not planned` / superseded por ADR-0154, sin reintroducir código.

## Evidencia

1. La implementación histórica de backup SQLite sí existió en la rama
   `feat/backup-dump-and-cloud` (`28348cd`): `VACUUM INTO`, stream al Cloud y piezas de restore.
2. Esa rama está contenida en `main`; no es trabajo perdido o pendiente de cherry-pick.
3. ADR-0154 cambió el producto a Cloud-only/PostgreSQL-only y retiró explícitamente esa capa:
   - `c10137c`: elimina runtime local/Tauri + SQLite.
   - `ba2876c`: elimina el subsistema host backup ya no operativo.
   - `112c01d`: elimina los últimos huérfanos de backup y `HUB_SQLITE_PATH`.
4. `ARQUITECTURA.md` fija que los backups actuales son responsabilidad de la plataforma
   PostgreSQL (pgBackRest/PITR), no de un módulo dentro del Hub.

El criterio original de #41 —backup/restore de `erplora.db` para una instalación Local sin base
remota— no puede cumplirse en la arquitectura vigente porque ni `erplora.db`, ni SQLite, ni el
producto Local existen. Recuperar aquel código sería una regresión contra ADR-0154 y tocaría un
producto expresamente excluido por el solicitante.

Texto sugerido al cerrar: “Superseded by ADR-0154. The former SQLite backup implementation was
merged and then intentionally removed with the Local/SQLite runtime. Hub Cloud backups now belong
to the managed PostgreSQL platform (pgBackRest/PITR); no Hub module or restore swap remains.”

