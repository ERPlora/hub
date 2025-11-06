"""
Validador de plugins para CPOS Hub

Valida que los plugins cumplan con:
1. Estructura correcta de plugin.json
2. Dependencias permitidas (whitelist)
3. Compatibilidad con versión de CPOS
4. Seguridad (no código malicioso)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.plugin_allowed_deps import (
    PLUGIN_ALLOWED_DEPENDENCIES,
    is_dependency_allowed,
    get_allowed_dependencies_list,
)

logger = logging.getLogger(__name__)


class PluginValidationError(Exception):
    """Error de validación de plugin"""
    pass


class PluginValidator:
    """
    Validador de plugins CPOS Hub

    Valida estructura, dependencias y seguridad de plugins antes de instalar.
    """

    REQUIRED_FIELDS = [
        'plugin_id',
        'name',
        'version',
        'description',
        'author',
    ]

    FORBIDDEN_IMPORTS = [
        'os.system',
        'subprocess',
        'eval',
        'exec',
        '__import__',
        'compile',
        'open',  # Permitido pero con restricciones
    ]

    def __init__(self, plugin_path: Path):
        """
        Inicializa el validador

        Args:
            plugin_path: Ruta al directorio del plugin
        """
        self.plugin_path = Path(plugin_path)
        self.plugin_json_path = self.plugin_path / 'plugin.json'
        self.plugin_data: Optional[Dict] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> Tuple[bool, List[str], List[str]]:
        """
        Ejecuta todas las validaciones

        Returns:
            Tuple[bool, List[str], List[str]]: (es_válido, errores, warnings)
        """
        try:
            # 1. Validar estructura de archivos
            self._validate_structure()

            # 2. Validar plugin.json
            self._validate_plugin_json()

            # 3. Validar dependencias
            self._validate_dependencies()

            # 4. Validar compatibilidad
            self._validate_compatibility()

            # 5. Validar seguridad (básico)
            self._validate_security()

            is_valid = len(self.errors) == 0
            return is_valid, self.errors, self.warnings

        except Exception as e:
            logger.exception(f"Error inesperado validando plugin: {e}")
            self.errors.append(f"Error inesperado: {str(e)}")
            return False, self.errors, self.warnings

    def _validate_structure(self):
        """Valida que existan los archivos requeridos"""
        if not self.plugin_path.exists():
            raise PluginValidationError(f"Directorio no existe: {self.plugin_path}")

        if not self.plugin_path.is_dir():
            raise PluginValidationError(f"No es un directorio: {self.plugin_path}")

        # plugin.json es obligatorio
        if not self.plugin_json_path.exists():
            raise PluginValidationError("Archivo plugin.json no encontrado")

        # __init__.py es obligatorio (debe ser un paquete Python)
        init_file = self.plugin_path / '__init__.py'
        if not init_file.exists():
            self.errors.append("Archivo __init__.py no encontrado")

    def _validate_plugin_json(self):
        """Valida el contenido de plugin.json"""
        try:
            with open(self.plugin_json_path, 'r', encoding='utf-8') as f:
                self.plugin_data = json.load(f)
        except json.JSONDecodeError as e:
            raise PluginValidationError(f"plugin.json inválido: {e}")

        # Validar campos requeridos
        for field in self.REQUIRED_FIELDS:
            if field not in self.plugin_data:
                self.errors.append(f"Campo requerido faltante: '{field}'")

        # Validar tipos
        if 'plugin_id' in self.plugin_data:
            if not isinstance(self.plugin_data['plugin_id'], str):
                self.errors.append("'plugin_id' debe ser string")
            elif not self.plugin_data['plugin_id'].replace('_', '').replace('-', '').isalnum():
                self.errors.append("'plugin_id' solo puede contener letras, números, guiones y guiones bajos")

        if 'version' in self.plugin_data:
            if not isinstance(self.plugin_data['version'], str):
                self.errors.append("'version' debe ser string")
            # TODO: Validar formato semver

    def _validate_dependencies(self):
        """Valida que las dependencias estén permitidas"""
        if 'dependencies' not in self.plugin_data:
            return  # Sin dependencias está OK

        dependencies = self.plugin_data.get('dependencies', {})

        # Validar dependencias Python
        python_deps = dependencies.get('python', [])
        if not isinstance(python_deps, list):
            self.errors.append("'dependencies.python' debe ser una lista")
            return

        for dep in python_deps:
            if not isinstance(dep, str):
                self.errors.append(f"Dependencia inválida (debe ser string): {dep}")
                continue

            # Validar que esté en la whitelist
            if not is_dependency_allowed(dep):
                # Extraer nombre del paquete para mensaje de error
                pkg_name = dep.split('>=')[0].split('==')[0].strip()
                self.errors.append(
                    f"❌ Dependencia NO permitida: '{pkg_name}'\n"
                    f"   Dependencias permitidas: {', '.join(list(PLUGIN_ALLOWED_DEPENDENCIES.keys())[:5])}...\n"
                    f"   Ver lista completa en: config/plugin_allowed_deps.py"
                )

        # Validar dependencias de otros plugins
        plugin_deps = dependencies.get('plugins', [])
        if plugin_deps and not isinstance(plugin_deps, list):
            self.errors.append("'dependencies.plugins' debe ser una lista")

    def _validate_compatibility(self):
        """Valida compatibilidad con versión de CPOS"""
        if 'compatibility' not in self.plugin_data:
            self.warnings.append("No se especifica compatibilidad (campo 'compatibility')")
            return

        compat = self.plugin_data['compatibility']

        # TODO: Validar contra versión actual de CPOS
        min_version = compat.get('min_cpos_version')
        max_version = compat.get('max_cpos_version')

        if not min_version:
            self.warnings.append("No se especifica 'min_cpos_version'")

        if not max_version:
            self.warnings.append("No se especifica 'max_cpos_version'")

    def _validate_security(self):
        """Validaciones básicas de seguridad"""
        # TODO: Implementar análisis estático de código Python
        # - Detectar imports peligrosos (os.system, subprocess, eval, exec)
        # - Detectar acceso a filesystem fuera del sandbox
        # - Detectar network requests a IPs privadas

        # Por ahora, solo warnings
        python_files = list(self.plugin_path.glob('**/*.py'))

        for py_file in python_files:
            try:
                content = py_file.read_text(encoding='utf-8')

                # Buscar imports peligrosos
                for forbidden in ['subprocess', 'os.system', 'eval(', 'exec(']:
                    if forbidden in content:
                        self.warnings.append(
                            f"⚠️  Código potencialmente peligroso en {py_file.name}: '{forbidden}'"
                        )

            except Exception as e:
                self.warnings.append(f"No se pudo analizar {py_file.name}: {e}")

    def get_plugin_info(self) -> Optional[Dict]:
        """
        Retorna información del plugin si es válida

        Returns:
            Dict con datos del plugin o None si no se ha validado
        """
        return self.plugin_data


def validate_plugin(plugin_path: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Función helper para validar un plugin

    Args:
        plugin_path: Ruta al directorio del plugin

    Returns:
        Tuple[bool, List[str], List[str]]: (es_válido, errores, warnings)

    Example:
        >>> is_valid, errors, warnings = validate_plugin(Path('/tmp/products'))
        >>> if not is_valid:
        ...     print(f"Errores: {errors}")
    """
    validator = PluginValidator(plugin_path)
    return validator.validate()


def get_allowed_dependencies_help() -> str:
    """
    Retorna mensaje de ayuda con dependencias permitidas

    Returns:
        str: Mensaje formateado con lista de dependencias
    """
    deps = get_allowed_dependencies_list()
    return (
        "📦 Dependencias permitidas para plugins:\n\n"
        + "\n".join(f"  ✅ {dep}" for dep in deps)
        + f"\n\nTotal: {len(deps)} librerías disponibles"
    )


if __name__ == '__main__':
    # Test del validador
    import sys

    if len(sys.argv) < 2:
        print("Uso: python plugin_validator.py /path/to/plugin")
        print()
        print(get_allowed_dependencies_help())
        sys.exit(1)

    plugin_path = Path(sys.argv[1])
    is_valid, errors, warnings = validate_plugin(plugin_path)

    print(f"📦 Validando plugin: {plugin_path}")
    print()

    if warnings:
        print("⚠️  Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    if errors:
        print("❌ Errores:")
        for error in errors:
            print(f"  - {error}")
        print()
        print("❌ Plugin inválido")
        sys.exit(1)
    else:
        print("✅ Plugin válido")
        sys.exit(0)
