# Sistema de Dependencias para Modules

## 🎯 Problema

PyInstaller crea un ejecutable congelado donde:
- ❌ No hay `pip` disponible
- ❌ No se pueden instalar paquetes nuevos después de empaquetar
- ❌ Los modules NO pueden instalar sus propias dependencias

## 💡 Soluciones Posibles

### Opción 1: Python Embebido (RECOMENDADO) ⭐

Empaquetar un Python completo (no congelado) junto con la aplicación.

**Ventajas:**
- ✅ Los modules pueden instalar dependencias con pip
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
│       └── modules/
│           ├── .venv/ (virtualenv para modules)
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
    """Configura Python embebido para modules"""
    if getattr(sys, 'frozen', False):
        python_home = bundle_dir / 'python'
        os.environ['PYTHONHOME'] = str(python_home)
        os.environ['PATH'] = f"{python_home / 'bin'}:{os.environ['PATH']}"

        # Crear venv para modules si no existe
        modules_venv = app_dir / 'modules' / '.venv'
        if not modules_venv.exists():
            subprocess.run([
                str(python_home / 'bin' / 'python3'),
                '-m', 'venv',
                str(modules_venv)
            ])
```

3. **Sistema de instalación de modules:**
```python
# En hub/apps/modules/installer.py
class ModuleInstaller:
    def install_module(self, module_path):
        """Instala un module y sus dependencias"""
        # 1. Leer module.json
        module_json = self.read_module_json(module_path)

        # 2. Instalar dependencias Python
        dependencies = module_json.get('dependencies', {}).get('python', [])
        if dependencies:
            self.install_dependencies(dependencies)

        # 3. Instalar module
        self.copy_module_files(module_path)

        # 4. Ejecutar migraciones
        self.run_migrations(module_json['module_id'])

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
            return bundle_dir / 'modules' / '.venv' / 'bin' / 'pip'
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
- ⚠️ Modules limitados a dependencias pre-empaquetadas
- ⚠️ Menos flexible

**Implementación:**

1. **Definir lista de librerías comunes permitidas:**
```python
# En hub/config/module_allowed_deps.py
ALLOWED_MODULE_DEPENDENCIES = {
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

3. **Validación en module.json:**
```python
# En hub/apps/modules/validator.py
class ModuleValidator:
    def validate_dependencies(self, module_json):
        """Valida que las dependencias del module estén permitidas"""
        dependencies = module_json.get('dependencies', {}).get('python', [])

        for dep in dependencies:
            pkg_name = dep.split('>=')[0].split('==')[0]
            if pkg_name not in ALLOWED_MODULE_DEPENDENCIES:
                raise ModuleValidationError(
                    f"Dependency '{pkg_name}' is not allowed. "
                    f"Allowed: {list(ALLOWED_MODULE_DEPENDENCIES.keys())}"
                )
```

### Opción 3: Hybrid Approach (EQUILIBRADO) ⭐⭐

Combinar ambas: Python embebido minimal + lista de dependencias pre-empaquetadas.

**Ventajas:**
- ✅ Modules comunes funcionan out-of-the-box (pre-bundled)
- ✅ Modules avanzados pueden instalar dependencias (embedded Python)
- ✅ Mejor experiencia de usuario

**Implementación:**

1. **Pre-empaquetar dependencias comunes** (Opción 2)
2. **Incluir pip embebido** para casos especiales:
```python
# En module installer
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
            raise ModuleError(
                f"Dependency '{dep}' not available. "
                f"Please contact CPOS support."
            )
```

## 🎯 Recomendación

**Para CPOS Hub, recomiendo Opción 3 (Hybrid):**

1. **Fase 1 (AHORA):** Implementar Opción 2 (Pre-bundled)
   - Lista curada de 10-15 librerías más comunes
   - Validación estricta en module.json
   - Documentar librerías disponibles

2. **Fase 2 (FUTURO):** Agregar Python embebido (Opción 1)
   - Para modules enterprise/avanzados
   - Requiere aprobación del owner
   - Con sandboxing de seguridad

## 📋 Librerías Pre-empaquetadas Recomendadas

```python
# Para incluir en main.spec
MODULE_COMMON_DEPENDENCIES = [
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

1. **Sandboxing:** Modules NO deben poder ejecutar código arbitrario
2. **Whitelist:** Solo dependencias aprobadas
3. **Validación:** Verificar module.json antes de instalar
4. **Checksums:** Verificar integridad de paquetes

## 📖 Documentación para Desarrolladores

```markdown
# Desarrollo de Modules - Dependencias

## Dependencias Disponibles

Tu module puede usar las siguientes librerías:

- `Pillow>=10.0.0` - Manipulación de imágenes
- `openpyxl>=3.1.0` - Lectura/escritura de Excel
- `qrcode>=7.4.0` - Generación de QR codes
- `reportlab>=4.0.0` - Generación de PDFs
- ... (lista completa)

## Cómo declarar dependencias

En tu `module.json`:

```json
{
  "module_id": "mi-module",
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

1. Crear `hub/config/module_allowed_deps.py`
2. Actualizar `main.spec` con las dependencias comunes
3. Crear `hub/apps/modules/validator.py`
4. Actualizar documentación en CLAUDE.md

¿Procedo con la implementación?
