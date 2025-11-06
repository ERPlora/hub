# Sistema de Dependencias para Plugins

## 🎯 Problema

PyInstaller crea un ejecutable congelado donde:
- ❌ No hay `pip` disponible
- ❌ No se pueden instalar paquetes nuevos después de empaquetar
- ❌ Los plugins NO pueden instalar sus propias dependencias

## 💡 Soluciones Posibles

### Opción 1: Python Embebido (RECOMENDADO) ⭐

Empaquetar un Python completo (no congelado) junto con la aplicación.

**Ventajas:**
- ✅ Los plugins pueden instalar dependencias con pip
- ✅ Máxima flexibilidad
- ✅ Experiencia similar a desarrollo

**Desventajas:**
- ⚠️ Bundle más grande (~100MB adicionales)
- ⚠️ Requiere arquitectura más compleja

**Arquitectura:**
```
CPOS Hub.app/
├── Contents/
│   ├── MacOS/
│   │   └── main (launcher)
│   └── Resources/
│       ├── hub/ (Django app)
│       ├── python/ (Python embebido completo)
│       │   ├── bin/
│       │   │   ├── python3
│       │   │   └── pip
│       │   └── lib/
│       └── plugins/
│           ├── .venv/ (virtualenv para plugins)
│           └── installed/
│               ├── products/
│               └── inventory/
```

**Implementación:**

1. **Modificar main.spec para incluir Python embebido:**
```python
# En main.spec
import shutil
from pathlib import Path

# Copiar Python embebido
python_embed_src = Path(sys.prefix)  # Python actual
python_embed_dst = hub_root / '_python_embed'

# Crear Python embebido minimal
python_files = [
    (str(python_embed_src / 'bin/python3'), 'python/bin'),
    (str(python_embed_src / 'bin/pip3'), 'python/bin'),
    (str(python_embed_src / 'lib/python3.11'), 'python/lib/python3.11'),
]

datas.extend(python_files)
```

2. **Modificar main.py para inicializar Python embebido:**
```python
# En main.py
def setup_embedded_python():
    """Configura Python embebido para plugins"""
    if getattr(sys, 'frozen', False):
        python_home = bundle_dir / 'python'
        os.environ['PYTHONHOME'] = str(python_home)
        os.environ['PATH'] = f"{python_home / 'bin'}:{os.environ['PATH']}"

        # Crear venv para plugins si no existe
        plugins_venv = app_dir / 'plugins' / '.venv'
        if not plugins_venv.exists():
            subprocess.run([
                str(python_home / 'bin' / 'python3'),
                '-m', 'venv',
                str(plugins_venv)
            ])
```

3. **Sistema de instalación de plugins:**
```python
# En hub/apps/plugins/installer.py
class PluginInstaller:
    def install_plugin(self, plugin_path):
        """Instala un plugin y sus dependencias"""
        # 1. Leer plugin.json
        plugin_json = self.read_plugin_json(plugin_path)

        # 2. Instalar dependencias Python
        dependencies = plugin_json.get('dependencies', {}).get('python', [])
        if dependencies:
            self.install_dependencies(dependencies)

        # 3. Instalar plugin
        self.copy_plugin_files(plugin_path)

        # 4. Ejecutar migraciones
        self.run_migrations(plugin_json['plugin_id'])

    def install_dependencies(self, dependencies):
        """Instala dependencias usando pip del venv embebido"""
        pip_path = self.get_embedded_pip()
        for dep in dependencies:
            subprocess.run([
                str(pip_path),
                'install',
                dep
            ], check=True)

    def get_embedded_pip(self):
        """Retorna path al pip del Python embebido"""
        if getattr(sys, 'frozen', False):
            return bundle_dir / 'plugins' / '.venv' / 'bin' / 'pip'
        else:
            return 'pip'  # Desarrollo local
```

### Opción 2: Pre-bundled Dependencies (MÁS SIMPLE)

Incluir las dependencias más comunes pre-empaquetadas en la app.

**Ventajas:**
- ✅ Más simple de implementar
- ✅ Bundle más pequeño
- ✅ Más rápido

**Desventajas:**
- ⚠️ Plugins limitados a dependencias pre-empaquetadas
- ⚠️ Menos flexible

**Implementación:**

1. **Definir lista de librerías comunes permitidas:**
```python
# En hub/config/plugin_allowed_deps.py
ALLOWED_PLUGIN_DEPENDENCIES = {
    'Pillow': '>=10.0.0',
    'openpyxl': '>=3.1.0',
    'requests': '>=2.31.0',
    'pandas': '>=2.0.0',
    'qrcode': '>=7.4.0',
    'reportlab': '>=4.0.0',
    'python-barcode': '>=0.15.0',
}
```

2. **Incluir en main.spec:**
```python
# En main.spec
hiddenimports=[
    *collect_submodules('django'),
    *collect_submodules('PIL'),
    *collect_submodules('openpyxl'),
    *collect_submodules('requests'),
    *collect_submodules('pandas'),
    *collect_submodules('qrcode'),
    *collect_submodules('reportlab'),
    *collect_submodules('barcode'),
    # ... otras
]
```

3. **Validación en plugin.json:**
```python
# En hub/apps/plugins/validator.py
class PluginValidator:
    def validate_dependencies(self, plugin_json):
        """Valida que las dependencias del plugin estén permitidas"""
        dependencies = plugin_json.get('dependencies', {}).get('python', [])

        for dep in dependencies:
            pkg_name = dep.split('>=')[0].split('==')[0]
            if pkg_name not in ALLOWED_PLUGIN_DEPENDENCIES:
                raise PluginValidationError(
                    f"Dependency '{pkg_name}' is not allowed. "
                    f"Allowed: {list(ALLOWED_PLUGIN_DEPENDENCIES.keys())}"
                )
```

### Opción 3: Hybrid Approach (EQUILIBRADO) ⭐⭐

Combinar ambas: Python embebido minimal + lista de dependencias pre-empaquetadas.

**Ventajas:**
- ✅ Plugins comunes funcionan out-of-the-box (pre-bundled)
- ✅ Plugins avanzados pueden instalar dependencias (embedded Python)
- ✅ Mejor experiencia de usuario

**Implementación:**

1. **Pre-empaquetar dependencias comunes** (Opción 2)
2. **Incluir pip embebido** para casos especiales:
```python
# En plugin installer
def install_dependencies(self, dependencies):
    """Intenta usar pre-bundled, si no existe usa pip"""
    for dep in dependencies:
        pkg_name = self.extract_package_name(dep)

        # ¿Está pre-empaquetado?
        if self.is_prebundled(pkg_name):
            logger.info(f"✅ {pkg_name} ya está incluido")
            continue

        # ¿Tenemos pip embebido?
        if self.has_embedded_pip():
            logger.info(f"📦 Instalando {dep} con pip...")
            self.install_with_pip(dep)
        else:
            raise PluginError(
                f"Dependency '{dep}' not available. "
                f"Please contact CPOS support."
            )
```

## 🎯 Recomendación

**Para CPOS Hub, recomiendo Opción 3 (Hybrid):**

1. **Fase 1 (AHORA):** Implementar Opción 2 (Pre-bundled)
   - Lista curada de 10-15 librerías más comunes
   - Validación estricta en plugin.json
   - Documentar librerías disponibles

2. **Fase 2 (FUTURO):** Agregar Python embebido (Opción 1)
   - Para plugins enterprise/avanzados
   - Requiere aprobación del owner
   - Con sandboxing de seguridad

## 📋 Librerías Pre-empaquetadas Recomendadas

```python
# Para incluir en main.spec
PLUGIN_COMMON_DEPENDENCIES = [
    # Images & Media
    'Pillow',           # Manipulación de imágenes
    'qrcode',           # QR codes
    'python-barcode',   # Códigos de barras

    # Office & Reports
    'openpyxl',         # Excel
    'reportlab',        # PDF
    'python-docx',      # Word documents

    # Data
    'pandas',           # Análisis de datos
    'numpy',            # Cálculos numéricos

    # Network
    'requests',         # HTTP requests

    # Utils
    'python-dateutil',  # Date parsing
    'pytz',             # Timezone handling
]
```

## 🔒 Seguridad

**Consideraciones importantes:**

1. **Sandboxing:** Plugins NO deben poder ejecutar código arbitrario
2. **Whitelist:** Solo dependencias aprobadas
3. **Validación:** Verificar plugin.json antes de instalar
4. **Checksums:** Verificar integridad de paquetes

## 📖 Documentación para Desarrolladores

```markdown
# Desarrollo de Plugins - Dependencias

## Dependencias Disponibles

Tu plugin puede usar las siguientes librerías:

- `Pillow>=10.0.0` - Manipulación de imágenes
- `openpyxl>=3.1.0` - Lectura/escritura de Excel
- `qrcode>=7.4.0` - Generación de QR codes
- `reportlab>=4.0.0` - Generación de PDFs
- ... (lista completa)

## Cómo declarar dependencias

En tu `plugin.json`:

```json
{
  "plugin_id": "mi-plugin",
  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "openpyxl>=3.1.0"
    ]
  }
}
```

## Dependencias NO disponibles

Si necesitas una librería que no está en la lista:
1. Contacta a soporte técnico
2. Justifica el uso
3. Espera aprobación (evaluación de seguridad)
```

## 🚀 Siguiente Paso

¿Quieres que implemente **Opción 2 (Pre-bundled)** ahora mismo? Es la solución más práctica para empezar.

Los cambios necesarios serían:

1. Crear `hub/config/plugin_allowed_deps.py`
2. Actualizar `main.spec` con las dependencias comunes
3. Crear `hub/apps/plugins/validator.py`
4. Actualizar documentación en CLAUDE.md

¿Procedo con la implementación?
