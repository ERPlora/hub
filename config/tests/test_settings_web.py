"""What the web side serves: the static files, the hub's files, the languages and the time."""

import re

from django.conf import settings

from config.tests.settings_env import BASE_DIR, DEVELOPMENT_ENV, PRODUCTION_ENV


def test_whitenoise_storage_without_manifest_because_vite_already_hashes():
    backend = settings.STORAGES["staticfiles"]["BACKEND"]
    assert backend == "whitenoise.storage.CompressedStaticFilesStorage"
    assert "Manifest" not in backend
    assert settings.STATIC_URL == "/static/"
    assert settings.STATIC_ROOT == BASE_DIR / "staticfiles"


def test_the_hub_files_go_to_the_bucket_terraform_names(load_settings):
    # aws/stacks/prod/apps.tf hands the Hub's task AWS_STORAGE_BUCKET_NAME and AWS_REGION (base.storage).
    loaded = load_settings(**PRODUCTION_ENV, AWS_STORAGE_BUCKET_NAME="erplora-prod-hubs", AWS_REGION="eu-west-1")
    hub_files = loaded["STORAGES"]["hub_files"]
    assert hub_files["BACKEND"] == "storages.backends.s3.S3Storage"
    options = hub_files["OPTIONS"]
    assert (options["bucket_name"], options["region_name"]) == ("erplora-prod-hubs", "eu-west-1")
    # The rest of STORAGES is untouched.
    assert loaded["STORAGES"]["staticfiles"]["BACKEND"] == "whitenoise.storage.CompressedStaticFilesStorage"


def test_without_a_bucket_the_hub_files_go_under_media_root(load_settings, tmp_path):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert loaded["MEDIA_ROOT"] == BASE_DIR / "media"
    assert loaded["STORAGES"]["hub_files"] == {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": BASE_DIR / "media"},
    }
    moved = load_settings(**DEVELOPMENT_ENV, MEDIA_ROOT=str(tmp_path))
    assert moved["STORAGES"]["hub_files"]["OPTIONS"]["location"] == tmp_path


def test_the_media_directory_is_never_committed():
    assert "media/" in (BASE_DIR / ".gitignore").read_text().splitlines()


def test_only_vite_assets_are_immutable():
    immutable = re.compile(settings.WHITENOISE_IMMUTABLE_FILE_TEST)
    assert immutable.search("/static/spa/assets/main-4f2a.js")
    assert not immutable.search("/static/spa/favicon.svg")
    assert not immutable.search("/static/admin/js/core.js")


def test_spa_build_is_a_static_dir_only_once_built(load_settings):
    dist = BASE_DIR / "frontend" / "dist"
    dirs = load_settings(**DEVELOPMENT_ENV)["STATICFILES_DIRS"]
    assert (("spa", dist) in dirs) is dist.is_dir()


def test_languages_and_time():
    assert settings.LANGUAGE_CODE == "en"
    assert [code for code, _ in settings.LANGUAGES] == ["en", "es"]
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "Europe/Madrid"


def test_the_static_files_finders_add_the_documentation_images_of_the_modules():
    # base.catalog.AppImagesFinder publishes apps/<id>/docs/img/ as /static/catalog/<id>/img/.
    assert settings.STATICFILES_FINDERS == [
        "django.contrib.staticfiles.finders.FileSystemFinder",
        "django.contrib.staticfiles.finders.AppDirectoriesFinder",
        "base.catalog.AppImagesFinder",
    ]
