#!/usr/bin/env python3
"""
Build script for CPOS Hub
Builds executable for current platform using PyInstaller
"""

import sys
import platform
import subprocess
import shutil
from pathlib import Path
from version import __version__, get_full_version

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def get_platform_info():
    """Get current platform information"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    platforms = {
        'windows': 'windows',
        'darwin': 'macos',
        'linux': 'linux'
    }

    return {
        'system': platforms.get(system, system),
        'machine': machine,
        'python_version': platform.python_version(),
    }


def clean_build():
    """Clean previous build artifacts"""
    print_info("Cleaning previous build artifacts...")

    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print_success(f"Removed {dir_name}/")

    # Remove spec file if auto-generated
    if Path('CPOS-Hub.spec').exists():
        Path('CPOS-Hub.spec').unlink()
        print_success("Removed auto-generated spec file")


def check_dependencies():
    """Check if required dependencies are installed"""
    print_info("Checking dependencies...")

    try:
        import PyInstaller
        print_success(f"PyInstaller {PyInstaller.__version__} installed")
    except ImportError:
        print_error("PyInstaller not installed")
        print_info("Install with: pip install pyinstaller")
        return False

    # Check if requirements.txt dependencies are installed
    try:
        import django
        print_success(f"Django {django.__version__} installed")
    except ImportError:
        print_error("Django not installed")
        print_info("Install with: pip install -r requirements.txt")
        return False

    return True


def build_executable(platform_info):
    """Build executable using PyInstaller"""
    print_info(f"Building for {platform_info['system']}...")

    # Build command
    cmd = ['pyinstaller', 'build.spec', '--clean']

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print_success("Build completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error("Build failed")
        print(e.stderr)
        return False


def create_archive(platform_info):
    """Create distributable archive"""
    print_info("Creating distributable archive...")

    system = platform_info['system']
    version = get_full_version()

    dist_dir = Path('dist')
    if not dist_dir.exists():
        print_error("dist/ directory not found")
        return False

    # Archive name
    archive_name = f"CPOS-Hub-{version}-{system}"

    try:
        if system == 'windows':
            # Create ZIP for Windows
            shutil.make_archive(archive_name, 'zip', dist_dir, 'CPOS-Hub')
            print_success(f"Created {archive_name}.zip")

        elif system == 'macos':
            # Create ZIP for macOS (with .app bundle)
            shutil.make_archive(archive_name, 'zip', dist_dir, 'CPOS Hub.app')
            print_success(f"Created {archive_name}.zip")

        elif system == 'linux':
            # Create tar.gz for Linux
            shutil.make_archive(archive_name, 'gztar', dist_dir, 'CPOS-Hub')
            print_success(f"Created {archive_name}.tar.gz")

        return True

    except Exception as e:
        print_error(f"Failed to create archive: {e}")
        return False


def print_build_info(platform_info):
    """Print build information"""
    print_header("Build Information")
    print(f"Version:       {get_full_version()}")
    print(f"Platform:      {platform_info['system']} ({platform_info['machine']})")
    print(f"Python:        {platform_info['python_version']}")
    print()


def main():
    """Main build process"""
    print_header(f"CPOS Hub Builder v{__version__}")

    # Get platform info
    platform_info = get_platform_info()
    print_build_info(platform_info)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Clean previous builds
    clean_build()

    # Build executable
    if not build_executable(platform_info):
        sys.exit(1)

    # Create archive
    if not create_archive(platform_info):
        sys.exit(1)

    # Success message
    print_header("Build Complete!")
    print_success(f"CPOS Hub {get_full_version()} built successfully for {platform_info['system']}")
    print()
    print_info("Output files:")
    print(f"  • dist/CPOS-Hub/")
    print(f"  • CPOS-Hub-{get_full_version()}-{platform_info['system']}.*")
    print()


if __name__ == '__main__':
    main()
