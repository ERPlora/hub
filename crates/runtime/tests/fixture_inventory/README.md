Fixture autocontenido para los tests del runtime y del server. NO es un módulo de producción
(ese vive en `../../../../../modules-workspace/modules/inventory/`, raíz del monorepo); se duplica
aquí para que los tests no dependan de ficheros que herramientas externas puedan modificar.
Mantener en sync con `modules-workspace/modules/inventory/` si cambia el contrato del manifest.
