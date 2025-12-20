"""
Validador de modules para CPOS Hub

Valida que los modules cumplan con:
1. Estructura correcta de module.json
2. Dependencias permitidas (whitelist)
3. Compatibilidad con versión de CPOS
4. Seguridad (no código malicioso)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.module_allowed_deps import (
    MODULE_ALLOWED_DEPENDENCIES,
    is_dependency_allowed,
    get_allowed_dependencies_list,
)

logger = logging.getLogger(__name__)


class ModuleValidationError(Exception):
    """Error de validación de module"""
    pass


class ModuleValidator:
    """
    Validador de modules CPOS Hub

    Valida estructura, dependencias y seguridad de modules antes de instalar.
    """

    REQUIRED_FIELDS = [
        'module_id',
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

    def __init__(self, module_path: Path):
        """
        Inicializa el validador

        Args:
            module_path: Ruta al directorio del module
        """
        self.module_path = Path(module_path)
        self.module_json_path = self.module_path / 'module.json'
        self.module_data: Optional[Dict] = None
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

            # 2. Validar module.json
            self._validate_module_json()

            # 3. Validar dependencias
            self._validate_dependencies()

            # 4. Validar compatibilidad
            self._validate_compatibility()

            # 5. Validar seguridad (básico)
            self._validate_security()

            is_valid = len(self.errors) == 0
            return is_valid, self.errors, self.warnings

        except Exception as e:
            logger.exception(f"Error inesperado validando module: {e}")
            self.errors.append(f"Error inesperado: {str(e)}")
            return False, self.errors, self.warnings

    def _validate_structure(self):
        """Valida que existan los archivos requeridos"""
        if not self.module_path.exists():
            raise ModuleValidationError(f"Directorio no existe: {self.module_path}")

        if not self.module_path.is_dir():
            raise ModuleValidationError(f"No es un directorio: {self.module_path}")

        # module.json es obligatorio
        if not self.module_json_path.exists():
            raise ModuleValidationError("Archivo module.json no encontrado")

        # __init__.py es obligatorio (debe ser un paquete Python)
        init_file = self.module_path / '__init__.py'
        if not init_file.exists():
            self.errors.append("Archivo __init__.py no encontrado")

    def _validate_module_json(self):
        """Valida el contenido de module.json"""
        try:
            with open(self.module_json_path, 'r', encoding='utf-8') as f:
                self.module_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ModuleValidationError(f"module.json inválido: {e}")

        # Validar campos requeridos
        for field in self.REQUIRED_FIELDS:
            if field not in self.module_data:
                self.errors.append(f"Campo requerido faltante: '{field}'")

        # Validar tipos
        if 'module_id' in self.module_data:
            if not isinstance(self.module_data['module_id'], str):
                self.errors.append("'module_id' debe ser string")
            elif not self.module_data['module_id'].replace('_', '').replace('-', '').isalnum():
                self.errors.append("'module_id' solo puede contener letras, números, guiones y guiones bajos")

        if 'version' in self.module_data:
            if not isinstance(self.module_data['version'], str):
                self.errors.append("'version' debe ser string")
            # TODO: Validar formato semver

    def _validate_dependencies(self):
        """Valida que las dependencias estén permitidas"""
        if 'dependencies' not in self.module_data:
            return  # Sin dependencias está OK

        dependencies = self.module_data.get('dependencies', {})

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
                    f"[ERROR] Dependencia NO permitida: '{pkg_name}'\n"
                    f"   Dependencias permitidas: {', '.join(list(MODULE_ALLOWED_DEPENDENCIES.keys())[:5])}...\n"
                    f"   Ver lista completa en: config/module_allowed_deps.py"
                )

        # Validar dependencias de otros modules
        module_deps = dependencies.get('modules', [])
        if module_deps and not isinstance(module_deps, list):
            self.errors.append("'dependencies.modules' debe ser una lista")

    def _validate_compatibility(self):
        """Valida compatibilidad con versión de CPOS"""
        if 'compatibility' not in self.module_data:
            self.warnings.append("No se especifica compatibilidad (campo 'compatibility')")
            return

        compat = self.module_data['compatibility']

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
        python_files = list(self.module_path.glob('**/*.py'))

        for py_file in python_files:
            try:
                content = py_file.read_text(encoding='utf-8')

                # Buscar imports peligrosos
                for forbidden in ['subprocess', 'os.system', 'eval(', 'exec(']:
                    if forbidden in content:
                        self.warnings.append(
                            f"[WARNING] Código potencialmente peligroso en {py_file.name}: '{forbidden}'"
                        )

            except Exception as e:
                self.warnings.append(f"No se pudo analizar {py_file.name}: {e}")

    def get_module_info(self) -> Optional[Dict]:
        """
        Retorna información del module si es válida

        Returns:
            Dict con datos del module o None si no se ha validado
        """
        return self.module_data


def validate_module(module_path: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Función helper para validar un module

    Args:
        module_path: Ruta al directorio del module

    Returns:
        Tuple[bool, List[str], List[str]]: (es_válido, errores, warnings)

    Example:
        >>> is_valid, errors, warnings = validate_module(Path('/tmp/products'))
        >>> if not is_valid:
        ...     print(f"Errores: {errors}")
    """
    validator = ModuleValidator(module_path)
    return validator.validate()


def get_allowed_dependencies_help() -> str:
    """
    Retorna mensaje de ayuda con dependencias permitidas

    Returns:
        str: Mensaje formateado con lista de dependencias
    """
    deps = get_allowed_dependencies_list()
    return (
        "[INFO] Dependencias permitidas para modules:\n\n"
        + "\n".join(f"  [OK] {dep}" for dep in deps)
        + f"\n\nTotal: {len(deps)} librerías disponibles"
    )


if __name__ == '__main__':
    # Test del validador
    import sys

    if len(sys.argv) < 2:
        print("Uso: python module_validator.py /path/to/module")
        print()
        print(get_allowed_dependencies_help())
        sys.exit(1)

    module_path = Path(sys.argv[1])
    is_valid, errors, warnings = validate_module(module_path)

    print(f"[INFO] Validando module: {module_path}")
    print()

    if warnings:
        print("[WARNING] Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    if errors:
        print("[ERROR] Errores:")
        for error in errors:
            print(f"  - {error}")
        print()
        print("[ERROR] Module invalido")
        sys.exit(1)
    else:
        print("[OK] Module valido")
        sys.exit(0)
