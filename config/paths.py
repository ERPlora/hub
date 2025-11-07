r"""
Path Management for CPOS Hub

Maneja las rutas de datos de usuario según la plataforma (Windows, macOS, Linux).
Todos los datos persisten fuera de la aplicación para permitir actualizaciones limpias.

Estructura de directorios:
    Windows:  C:\Users\<usuario>\AppData\Local\CPOSHub\
    macOS:    /Users/<usuario>/Library/Application Support/CPOSHub/
    Linux:    /home/<usuario>/.cpos-hub/

Subdirectorios:
    - db/              Base de datos SQLite
    - media/           Archivos subidos (imágenes, etc.)
    - plugins/         Plugins instalados y sus datos
    - reports/         Reportes generados (PDF, Excel)
    - logs/            Logs de la aplicación
    - backups/         Backups automáticos de la DB
"""

import os
import sys
from pathlib import Path
from typing import Dict


class DataPaths:
    """
    Gestiona las rutas de datos de usuario multiplataforma.
    """

    APP_NAME = "CPOSHub"
    APP_NAME_HIDDEN = ".cpos-hub"  # Para Linux

    def __init__(self):
        self.platform = sys.platform
        self._base_dir = None
        self._ensure_directories()

    @property
    def base_dir(self) -> Path:
        r"""
        Directorio base de datos de usuario según la plataforma.

        Returns:
            Path: Directorio base
                - Windows: C:\Users\<user>\AppData\Local\CPOSHub
                - macOS: /Users/<user>/Library/Application Support/CPOSHub
                - Linux: /home/<user>/.cpos-hub
        """
        if self._base_dir is None:
            if self.platform == "win32":
                # Windows: AppData\Local
                local_appdata = os.getenv("LOCALAPPDATA")
                if not local_appdata:
                    # Fallback si LOCALAPPDATA no existe
                    local_appdata = Path.home() / "AppData" / "Local"
                self._base_dir = Path(local_appdata) / self.APP_NAME

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
    def plugins_dir(self) -> Path:
        """Directorio de plugins instalados"""
        return self.base_dir / "plugins"

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
            "plugins": self.plugins_dir,
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
            self.plugins_dir,
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

    def get_plugin_data_dir(self, plugin_id: str) -> Path:
        """
        Retorna el directorio de datos de un plugin específico.

        Args:
            plugin_id: ID del plugin

        Returns:
            Path: Directorio de datos del plugin
        """
        plugin_data_dir = self.plugins_dir / plugin_id / "data"
        plugin_data_dir.mkdir(parents=True, exist_ok=True)
        return plugin_data_dir

    def get_plugin_media_dir(self, plugin_id: str) -> Path:
        """
        Retorna el directorio de media de un plugin específico.

        Args:
            plugin_id: ID del plugin

        Returns:
            Path: Directorio de media del plugin
        """
        plugin_media_dir = self.media_dir / "plugins" / plugin_id
        plugin_media_dir.mkdir(parents=True, exist_ok=True)
        return plugin_media_dir

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


def get_plugins_dir() -> Path:
    """Retorna el directorio de plugins"""
    return data_paths.plugins_dir


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
    paths = get_data_paths()
    print(f"Platform: {paths.platform}")
    print(f"\nBase directory: {paths.base_dir}")
    print(f"\nAll paths:")
    for name, path in paths.get_all_paths().items():
        exists = "[OK]" if path.exists() else "[MISSING]"
        print(f"  {exists} {name:15} -> {path}")
