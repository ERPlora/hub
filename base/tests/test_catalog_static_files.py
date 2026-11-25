"""base/catalog/static_files.py: ``AppImagesFinder`` publishes ``apps/<id>/docs/img/`` as
``catalog/<id>/img/``, never through a symbolic link. The last test runs the real pipeline.
"""

from pathlib import Path

import pytest
from django.contrib.staticfiles import finders

from base.catalog.app_registry import build_registry
from base.catalog.static_files import AppImagesFinder
from base.tests.apps_on_disk import ICONS, SYMLINKS, link, linked_module, module, outside_files, problems


def test_the_finder_publishes_docs_img_under_catalog_and_nothing_else(tmp_path):
    files = (
        "docs/img/list.png",
        "docs/img/sub/photo.webp",
        "docs/img/diagram.svg",
        "docs/img/.hidden.png",
        "docs/img/.cache/x.png",
        "docs/img/script.py",
        "docs/other.png",
        "WORKBOOK.md",
        "WORKBOOK.en.md",
        "apps.py",
    )
    finder = AppImagesFinder(configs=[module(tmp_path, images=files)])

    listed = sorted(f"{storage.prefix}/{path}" for path, storage in finder.list(None))

    assert listed == [
        "catalog/things/img/list.png",
        "catalog/things/img/sub/photo.webp",
    ]


def test_the_finder_finds_one_image_by_its_static_path(tmp_path):
    config = module(tmp_path, images=("docs/img/list.png", "docs/img/diagram.svg"))
    finder = AppImagesFinder(configs=[config])

    assert finder.find("catalog/things/img/list.png") == str(
        tmp_path / "things" / "docs" / "img" / "list.png"
    )
    assert finder.find("catalog/things/img/list.png", find_all=True) == [
        str(tmp_path / "things" / "docs" / "img" / "list.png")
    ]
    for missing in ("catalog/things/img/diagram.svg", "catalog/things/img/nope.png", "catalog/other/img/list.png",
                    "catalog/things/img/../WORKBOOK.md", "catalog/things/WORKBOOK.md", "spa/main.js"):  # fmt: skip
        assert finder.find(missing) == []


def test_the_finder_skips_ignored_patterns(tmp_path):
    finder = AppImagesFinder(
        configs=[module(tmp_path, images=("docs/img/a.png", "docs/img/b.gif"))]
    )
    assert [path for path, _ in finder.list(["*.gif"])] == ["a.png"]


def test_the_finder_skips_platform_apps_and_modules_without_images(tmp_path):
    configs = [
        module(tmp_path, "base", kind="platform", images=("docs/img/a.png",)),
        module(tmp_path, "things"),
    ]
    assert list(AppImagesFinder(configs=configs).list(None)) == []


def test_the_attack_link_resolves_to_the_settings(tmp_path):
    """The premise of the tests below: without the check, x.png would be the settings file."""
    config = linked_module(tmp_path, "docs/img/x.png", "../../../config/settings.py")

    assert (
        Path(config.path) / "docs/img/x.png"
    ).read_text() == "SECRET_KEY = 'leaked'\n"


@pytest.mark.parametrize(("path", "target", "static"), SYMLINKS)
def test_the_finder_publishes_nothing_through_a_symbolic_link(
    tmp_path, path, target, static
):
    finder = AppImagesFinder(configs=[linked_module(tmp_path, path, target)])

    assert list(finder.list(None)) == []
    assert finder.find(static) == []
    assert finder.find(static, find_all=True) == []


def test_a_real_image_next_to_a_symbolic_link_is_still_published(tmp_path):
    outside_files(tmp_path)
    config = module(tmp_path, images=("docs/img/list.png",))
    link(config, "docs/img/x.png", "../../../config/settings.py")
    finder = AppImagesFinder(configs=[config])

    assert [path for path, _ in finder.list(None)] == ["list.png"]
    assert finder.find("catalog/things/img/list.png") == str(
        Path(config.path) / "docs" / "img" / "list.png"
    )
    assert finder.find("catalog/things/img/x.png") == []
    [problem] = problems([config])
    assert "replace docs/img/x.png " in problem
    assert "list.png" not in problem


def test_a_hidden_symbolic_link_is_neither_published_nor_reported(tmp_path):
    outside_files(tmp_path)
    config = module(tmp_path, images=("docs/img/list.png",))
    link(config, "docs/img/.x.png", "../../../config/settings.py")

    assert build_registry([config], icons=ICONS)
    assert [path for path, _ in AppImagesFinder(configs=[config]).list(None)] == [
        "list.png"
    ]


def test_the_static_files_pipeline_finds_the_real_demo_image():
    # What collectstatic copies into STATIC_ROOT in the image's build (settings.STATICFILES_FINDERS).
    found = finders.find("catalog/demo/img/items-list.png")
    assert found and found.endswith("apps/demo/docs/img/items-list.png")
    assert finders.find("catalog/demo/WORKBOOK.md") is None
