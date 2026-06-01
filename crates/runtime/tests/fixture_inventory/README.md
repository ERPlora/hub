Fixture autocontenido para los tests del runtime y del server. NO es un módulo de producción
(ese vive en `modules/inventory/`); se duplica aquí para que los tests no dependan de ficheros
que herramientas externas puedan modificar. Mantener en sync con `modules/inventory/` si cambia
el contrato del manifest.
