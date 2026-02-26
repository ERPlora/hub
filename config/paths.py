r"""
Path Management for ERPlora Hub

Maneja las rutas de datos de usuario según el ENTORNO (Docker vs Local) y PLATAFORMA.
Todos los datos persisten fuera de la aplicación para permitir actualizaciones limpias.

DETECCIÓN DE ENTORNO:
    1. Variable DEPLOYMENT_MODE='web' → Docker
    2. Archivo /.dockerenv existe → Docker
    3. /proc/1/cgroup contiene 'docker' → Docker
    4. De lo contrario → Local (desarrollo)

PATHS POR ENTORNO:

    DOCKER (Web/Cloud):
        Base:     /app/
        DB:       /app/db/db.sqlite3
        Media:    /app/media/
        Modules:  /app/modules/
        Logs:     /app/logs/
        Backups:  /app/backups/

        IMPORTANTE: Estos directorios se montan como volúmenes Docker persistentes
                    para que los datos sobrevivan recreaciones del contenedor.

    LOCAL (Desarrollo):
        macOS:
            Base:     /Users/<usuario>/Library/Application Support/ERPloraHub/

        Linux:
            Base:     /home/<usuario>/.erplora-hub/

Subdirectorios (comunes a todos los entornos):
    - db/              Base de datos SQLite
    - media/           Archivos subidos (imágenes, logos, etc.)
    - modules/         Modules instalados y sus datos
    - reports/         Reportes generados (PDF, Excel)
    - logs/            Logs de la aplicación
    - backups/         Backups automáticos de la DB
    - temp/            Archivos temporales
"""

import os
import sys
from pathlib import Path
from typing import Dict
from decouple import config


def is_docker_environment() -> bool:
    """
    Detecta si estamos corriendo en un contenedor Docker.

    Returns:
        bool: True si estamos en Docker, False si no
    """
    # Método 1: Variable de entorno DEPLOYMENT_MODE
    deployment_mode = config('DEPLOYMENT_MODE', default='local')
    if deployment_mode == 'web':
        return True

    # Método 2: Verificar archivo /.dockerenv
    if os.path.exists('/.dockerenv'):
        return True

    # Método 3: Verificar cgroup (Linux containers)
    try:
        with open('/proc/1/cgroup', 'r') as f:
            if 'docker' in f.read():
                return True
    except Exception:
        pass

    return False


class DataPaths:
    """
    Gestiona las rutas de datos de usuario multiplataforma.
    """

    APP_NAME = "ERPloraHub"
    APP_NAME_HIDDEN = ".erplora-hub"  # Para Linux

    def __init__(self):
        self.platform = sys.platform
        self._base_dir = None
        self._ensure_directories()

    @property
    def base_dir(self) -> Path:
        r"""
        Directorio base de datos de usuario según el entorno.

        Returns:
            Path: Directorio base
              DOCKER (Web/Cloud):
                - /app (root del contenedor, montado como volumen)
              LOCAL (Desarrollo):
                - macOS: /Users/<user>/Library/Application Support/ERPloraHub
                - Linux: /home/<user>/.erplora-hub
        """
        if self._base_dir is None:
            # DATA_PATH from .env overrides platform defaults (local dev only)
            custom_path = config('DATA_PATH', default='')
            if custom_path:
                self._base_dir = Path(custom_path)

            elif is_docker_environment():
                # Docker: Usar /app como base (montado como volumen persistente)
                self._base_dir = Path("/app")

            elif self.platform == "darwin":
                # macOS: Library/Application Support
                self._base_dir = Path.home() / "Library" / "Application Support" / self.APP_NAME

            else:
                # Linux: directorio oculto en home
                self._base_dir = Path.home() / self.APP_NAME_HIDDEN

        return self._base_dir

    @property
    def database_dir(self) -> Path:
        """Directorio de la base de datos"""
        return self.base_dir / "db"

    @property
    def database_path(self) -> Path:
        """Ruta completa a db.sqlite3"""
        return self.database_dir / "db.sqlite3"

    @property
    def media_dir(self) -> Path:
        """Directorio de archivos media (imágenes subidas, etc.)"""
        return self.base_dir / "media"

    @property
    def modules_dir(self) -> Path:
        """Directorio de modules instalados"""
        return self.base_dir / "modules"

    @property
    def reports_dir(self) -> Path:
        """Directorio de reportes generados"""
        return self.base_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        """Directorio de logs"""
        return self.base_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        """Directorio de backups automáticos"""
        return self.base_dir / "backups"

    @property
    def temp_dir(self) -> Path:
        """Directorio temporal para procesamiento"""
        return self.base_dir / "temp"

    def get_all_paths(self) -> Dict[str, Path]:
        """
        Retorna todas las rutas configuradas.

        Returns:
            dict: Diccionario con todas las rutas
        """
        return {
            "base": self.base_dir,
            "database": self.database_path,
            "database_dir": self.database_dir,
            "media": self.media_dir,
            "modules": self.modules_dir,
            "reports": self.reports_dir,
            "logs": self.logs_dir,
            "backups": self.backups_dir,
            "temp": self.temp_dir,
        }

    def _ensure_directories(self):
        """
        Crea todos los directorios necesarios si no existen.
        """
        directories = [
            self.base_dir,
            self.database_dir,
            self.media_dir,
            self.modules_dir,
            self.reports_dir,
            self.logs_dir,
            self.backups_dir,
            self.temp_dir,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

            # En macOS y Linux, hacer el directorio base oculto (ya viene con . en Linux)
            if self.platform == "darwin":
                # En macOS, podemos añadir el flag de oculto
                try:
                    import subprocess
                    if directory == self.base_dir:
                        # Marcar como oculto en macOS
                        subprocess.run(
                            ["chflags", "hidden", str(directory)],
                            check=False,
                            capture_output=True
                        )
                except Exception:
                    pass  # Si falla, no es crítico

    def cleanup_temp(self):
        """
        Limpia el directorio temporal.
        """
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_module_data_dir(self, module_id: str) -> Path:
        """
        Retorna el directorio de datos de un module específico.

        Args:
            module_id: ID del module

        Returns:
            Path: Directorio de datos del module
        """
        module_data_dir = self.modules_dir / module_id / "data"
        module_data_dir.mkdir(parents=True, exist_ok=True)
        return module_data_dir

    def get_module_media_dir(self, module_id: str) -> Path:
        """
        Retorna el directorio de media de un module específico.

        Args:
            module_id: ID del module

        Returns:
            Path: Directorio de media del module
        """
        module_media_dir = self.media_dir / "modules" / module_id
        module_media_dir.mkdir(parents=True, exist_ok=True)
        return module_media_dir

    def __repr__(self):
        return f"<DataPaths platform={self.platform} base={self.base_dir}>"


# Instancia global
data_paths = DataPaths()


def get_data_paths() -> DataPaths:
    """
    Retorna la instancia global de DataPaths.

    Returns:
        DataPaths: Instancia de gestión de rutas
    """
    return data_paths


# Para uso directo
def get_database_path() -> Path:
    """Retorna la ruta de la base de datos"""
    return data_paths.database_path


def get_media_dir() -> Path:
    """Retorna el directorio de media"""
    return data_paths.media_dir


def get_modules_dir() -> Path:
    """Retorna el directorio de modules"""
    return data_paths.modules_dir


def get_reports_dir() -> Path:
    """Retorna el directorio de reportes"""
    return data_paths.reports_dir


def get_logs_dir() -> Path:
    """Retorna el directorio de logs"""
    return data_paths.logs_dir


def get_backups_dir() -> Path:
    """Retorna el directorio de backups"""
    return data_paths.backups_dir


if __name__ == "__main__":
    # Test y debugging
    print("=" * 70)
    print("ERPlora Hub - Path Configuration")
    print("=" * 70)

    # Detectar entorno
    is_docker = is_docker_environment()
    deployment_mode = config('DEPLOYMENT_MODE', default='local')

    print(f"\nEnvironment Detection:")
    print(f"  DEPLOYMENT_MODE:     {deployment_mode}")
    print(f"  Is Docker:           {is_docker}")
    print(f"  Platform:            {sys.platform}")

    # Mostrar paths
    paths = get_data_paths()
    print(f"\nBase directory:        {paths.base_dir}")

    print(f"\nAll paths:")
    for name, path in paths.get_all_paths().items():
        exists = "✓ EXISTS" if path.exists() else "✗ MISSING"
        print(f"  {exists:12} {name:15} -> {path}")

    print("\n" + "=" * 70)
    print("NOTES:")
    if is_docker:
        print("  Running in DOCKER - using /app as base")
        print("  Ensure volumes are mounted:")
        print("    -v hub_db:/app/db")
        print("    -v hub_media:/app/media")
        print("    -v hub_modules:/app/modules")
    else:
        print("  Running LOCAL - using OS-specific user directory")
        print(f"  Data will persist in: {paths.base_dir}")
    print("=" * 70)
