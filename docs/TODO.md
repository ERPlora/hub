# ERPlora Hub - TODO List

## Estado Actual: MVP OPERATIVO (2025-12-01)

### Hubs Desplegados en INT
- ✅ peluqueria-de-oana.a.erplora.com (running:healthy)
- ✅ peluqueria-de-flaviana.a.erplora.com (running:healthy)

---

## ✅ Completado Recientemente (2025-12-01)

### Fixes de Staticfiles
- ✅ Fix `no-more-tables.css` missing (eliminado - no se usaba)
- ✅ Fix `ionicons/dist/esm/ionicons.js` missing (añadido excepción en .gitignore)
- ✅ Todos los archivos de ionicons/dist añadidos a git (2729 archivos)

### SSO y Autenticación
- ✅ SSO desde Cloud funcionando
- ✅ Flujo `/setup-pin/` operativo después de SSO
- ✅ Login con PIN offline funcionando

### Infraestructura
- ✅ Redeploy automático via Dokploy API
- ✅ WhiteNoise staticfiles funcionando correctamente
- ✅ Volúmenes Docker persistentes para SQLite, media, modules

---

## 🚀 Pendiente

### Alta Prioridad

#### 1. Configuración Inicial del Hub (Setup Wizard)
- [ ] Wizard de configuración inicial cuando `is_configured = False`
- [ ] Configurar datos de tienda (nombre, dirección, moneda)
- [ ] Configurar impuestos (tax_rate, tax_included)
- [ ] Upload de logo de negocio

#### 2. Module Store desde Hub
- [ ] Vista de catálogo de modules desde Hub
- [ ] Instalación de modules via API Cloud
- [ ] Verificación de licencias/compras
- [ ] Actualización de modules

#### 3. Gestión de Empleados
- [ ] CRUD completo de empleados (LocalUser)
- [ ] Asignación de roles
- [ ] Gestión de PINs
- [ ] Permisos por rol

### Media Prioridad

#### 4. Sincronización con Cloud
- [ ] SyncQueue para operaciones offline
- [ ] Sincronización de configuración
- [ ] Sincronización de usuarios
- [ ] Logs de actividad hacia Cloud

#### 5. Modules de Negocio
- [ ] Module POS (Point of Sale)
- [ ] Module Inventory
- [ ] Module Sales
- [ ] Module Customers

#### 6. Impresión
- [ ] Configuración de impresoras
- [ ] Print preview modal
- [ ] Tickets térmicos (80mm)
- [ ] Facturas A4

### Baja Prioridad

#### 7. Backup y Restore
- [ ] Backup manual de SQLite
- [ ] Restore de backup
- [ ] Backup automático programado
- [ ] Export a Cloud (S3)

#### 8. Offline Mode
- [ ] Indicador de estado de conexión
- [ ] Modo degradado sin internet
- [ ] Queue de operaciones pendientes
- [ ] Auto-sync cuando vuelve conexión

---

## 🐛 Bugs Conocidos

- Ninguno actualmente

---

## 📋 Notas Técnicas

### Staticfiles
- WhiteNoise con `CompressedManifestStaticFilesStorage`
- Ionicons vendored en `static/ionicons/dist/`
- `.gitignore` tiene excepción `!static/ionicons/dist/`

### Autenticación
- SSO via cookies cross-domain (`.erplora.com`)
- JWT RS256 para API Cloud
- PIN local almacenado como hash en SQLite

### Deployment
- Docker containers via Dokploy
- Branch: `develop` para INT
- URL pattern: `{hub-slug}.a.erplora.com`

---

**Última actualización**: 2025-12-01
**Versión Hub**: develop branch
