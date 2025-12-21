# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Module system with dynamic loading from ZIP files
- Automatic dependency installation for modules
- Database conflict validation for modules
- PyInstaller build system for Windows/macOS/Linux
- Automated release management (release.py)
- GitHub Actions CI/CD for multi-platform builds
- Version management system (version.py)

### Changed
- Cross-platform temporary directory handling using tempfile.gettempdir()
- Simplified module installation by deleting ZIP immediately after extraction

### Fixed
- Windows compatibility for temporary file paths
