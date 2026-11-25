"""Static files: the documentation's images, published by ``AppImagesFinder``."""

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from django.contrib.staticfiles.finders import BaseFinder
from django.contrib.staticfiles.utils import matches_patterns
from django.core.files.storage import FileSystemStorage
from live.markdown import IMAGE_EXTENSIONS

from base.catalog.app_registry import IMAGES_DIR, _image_files, catalog_modules

#: Where the finder publishes them: ``/static/catalog/<id>/img/<file>``.
STATIC_PREFIX = "catalog"


def _through_symlink(app: Path, path: PurePosixPath) -> bool:
    """Whether ``app / path`` or any folder between ``app`` and it is a symbolic link."""
    return any(
        (app / PurePosixPath(*path.parts[:end])).is_symlink()
        for end in range(1, len(path.parts) + 1)
    )


class AppImagesFinder(BaseFinder):
    """Publishes each module's ``docs/img/**`` as ``catalog/<id>/img/**``, nothing else.

    Only ``live.markdown.IMAGE_EXTENSIONS`` (never ``svg``, which can carry script and would be served from the
    Hub admin's origin); never a ``WORKBOOK*.md``, code, a hidden file, a symbolic link (nor
    anything through one) or anything outside ``docs/img/``. ``collectstatic`` copies them to
    ``STATIC_ROOT`` (no hash: the path is stable) and ``runserver`` serves them at once.
    """

    def __init__(self, configs: Iterable | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storages: dict[str, FileSystemStorage] = {}
        #: ``{label: the module's folder}``, for the storages above.
        self.apps: dict[str, Path] = {}
        for config in catalog_modules(configs):
            app = Path(config.path)
            if (app / IMAGES_DIR).is_dir():
                storage = FileSystemStorage(location=app / IMAGES_DIR)
                storage.prefix = f"{STATIC_PREFIX}/{config.label}/img"
                self.storages[config.label] = storage
                self.apps[config.label] = app

    def list(self, ignore_patterns):
        for label, storage in self.storages.items():
            for path, problem in _image_files(self.apps[label]):
                if problem is not None:
                    continue
                relative = str(path.relative_to(IMAGES_DIR))
                if not (
                    ignore_patterns and matches_patterns(relative, ignore_patterns)
                ):
                    yield relative, storage

    def find(self, path, find_all=False, **kwargs):
        found = []
        for label, storage in self.storages.items():
            relative = path.removeprefix(f"{storage.prefix}/")
            if relative == path:
                continue
            parts = PurePosixPath(relative).parts
            if not parts or any(
                part in ("", "..") or part.startswith(".") for part in parts
            ):
                continue
            app, published = self.apps[label], IMAGES_DIR.joinpath(*parts)
            candidate = app / published
            if (
                candidate.suffix.lower() in IMAGE_EXTENSIONS
                and candidate.is_file()
                and not _through_symlink(app, published)
            ):
                if not find_all:
                    return str(candidate)
                found.append(str(candidate))
        return found
