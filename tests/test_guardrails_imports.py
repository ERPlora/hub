"""Each app imports only what it requires, base imports no app, and sibling modules never import each other in a circle.

import-linter checks the contracts of pyproject.toml's ``[tool.importlinter]`` (``uv run lint-imports``):

- One ``forbidden`` contract per app: it imports only itself, ``base``, ``live`` and the apps its ``LiveAppConfig``
  requires; every other app and the ``config``, ``control`` and ``shared`` packages are out of its reach. Only direct
  imports count, so an app may use what a required app uses in turn.
- ``base`` imports no app.
- ``acyclic_siblings``: no two children of ``base``, ``base.models``, ``base.tenancy``, ``control``, an app or a
  ``services``, ``queries`` or ``schemas`` package import each other, directly or round a longer circle. An import
  inside a function counts the same as one at the top of the module.

Tests are out of every contract (``**.tests.** -> **``): they may import whatever they check. What broke a contract
when it came in is frozen in that contract's ``ignore_imports``, which import-linter fails as soon as an entry matches
no import any more, and compared with where the branch left origin/main the frozen imports gain no entry between two
modules that had none. An entry may follow its code: when part of a frozen module moves into a submodule of its own
(``base/services/__init__.py`` into ``base/services/relay.py``), ``base.relay -> base.services`` may become, or come
with, ``base.relay -> base.services.relay``. It is the same dependency between the same two siblings.
"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from allow_list_base import REPO, file_at_base
from django.apps import apps as django_apps

CONFIG = "pyproject.toml"
TESTS_OUT = "**.tests.** -> **"
ROOT_PACKAGES = ["apps", "base", "config", "control", "shared"]
# The root packages besides apps and base, which no app reaches.
PLATFORM = ["config", "control", "shared"]
BASE_CONTRACT = "base-imports-no-app"
CYCLES_CONTRACT = "no-sibling-cycles"
CYCLE_ANCESTORS = {
    "base",
    "base.api",
    "base.blueprint",
    "base.models",
    "base.tenancy",
    "base.services",
    "base.queries",
    "base.schemas",
    "control",
    "control.services",
    "control.queries",
    "apps.*",
    "apps.*.services",
    "apps.*.queries",
    "apps.*.schemas",
}
NO_CONTRACTS_AT_BASE = (
    "pyproject.toml had no import contracts where the branch left origin/main: this is the commit that brings them"
)


def lint_imports(cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    script = Path(sys.executable).with_name("lint-imports")
    return subprocess.run([str(script), "--no-cache"], cwd=cwd, capture_output=True, text=True, check=False)


def importlinter_config(text: str) -> dict | None:
    return tomllib.loads(text).get("tool", {}).get("importlinter")


def current_config() -> dict:
    config = importlinter_config((REPO / CONFIG).read_text(encoding="utf-8"))
    assert config is not None, f"{CONFIG} has no [tool.importlinter] section"
    return config


def contracts_by_id(config: dict) -> dict[str, dict]:
    return {contract["id"]: contract for contract in config.get("contracts", [])}


def app_contract(module: str, required: list[str], every_app: list[str]) -> dict:
    """The contract an app's requires call for, under the id ``app-<label>``."""
    reach = {module, *required}
    return {
        "id": f"app-{module.rsplit('.', 1)[-1]}",
        "name": f"{module} imports only itself, base, live and the apps it requires",
        "type": "forbidden",
        "source_modules": [module],
        "forbidden_modules": sorted(app for app in every_app if app not in reach) + PLATFORM,
        "allow_indirect_imports": True,
        "ignore_imports": [TESTS_OUT],
    }


def base_contract() -> dict:
    return {
        "id": BASE_CONTRACT,
        "name": "base imports no app",
        "type": "forbidden",
        "source_modules": ["base"],
        "forbidden_modules": ["apps"],
        "allow_indirect_imports": True,
        "ignore_imports": [TESTS_OUT],
    }


def cycles_contract() -> dict:
    return {
        "id": CYCLES_CONTRACT,
        "name": "No sibling modules import each other in a circle",
        "type": "acyclic_siblings",
        "ancestors": sorted(CYCLE_ANCESTORS),
        "depth": 0,
        "ignore_imports": [TESTS_OUT],
    }


def requires_of_apps() -> dict[str, list[str]]:
    """Each installed app's package, with the packages of the apps it requires."""
    configs = [config for config in django_apps.get_app_configs() if getattr(config, "kind", None) == "app"]
    return {
        config.name: sorted(django_apps.get_app_config(label).name for label in config.requires) for config in configs
    }


def app_contract_mismatches(contracts: dict[str, dict], requires: dict[str, list[str]]) -> list[str]:
    """How the forbidden contracts of the apps differ from what their requires call for."""
    every_app = sorted(requires)
    expected = {module: app_contract(module, required, every_app) for module, required in requires.items()}
    found = {
        contract["source_modules"][0]: contract
        for contract in contracts.values()
        if contract.get("type") == "forbidden" and contract.get("source_modules", [""])[0].startswith("apps.")
    }
    problems = [f"{module}: no contract; add {json.dumps(expected[module])}" for module in sorted(expected.keys() - found)]
    problems += [f"{module}: a contract for an app that is not installed" for module in sorted(found.keys() - expected)]
    for module in sorted(expected.keys() & found.keys()):
        want, have = expected[module], found[module]
        problems += [
            f"{module}: {key} is {json.dumps(have.get(key))}, its requires call for {json.dumps(want[key])}"
            for key in ("id", "type", "forbidden_modules", "allow_indirect_imports")
            if have.get(key) != want[key]
        ]
    return problems


def normalized(entry: str) -> str:
    importer, imported = (part.strip() for part in entry.split("->"))
    return f"{importer} -> {imported}"


def frozen(config: dict) -> dict[str, set[str]]:
    """Each contract's frozen imports: its ignore_imports but the one that leaves the tests out."""
    return {
        contract["id"]: {normalized(entry) for entry in contract.get("ignore_imports", [])} - {TESTS_OUT}
        for contract in config.get("contracts", [])
    }


def carried(entry: str, before: set[str]) -> bool:
    """Whether ``entry`` joins the modules of one of ``before``, or submodules of them its code moved into."""

    def within(module: str, frozen_module: str) -> bool:
        return module == frozen_module or module.startswith(f"{frozen_module}.")

    importer, imported = entry.split(" -> ")
    return any(
        within(importer, old_importer) and within(imported, old_imported)
        for old_importer, old_imported in (old.split(" -> ") for old in before)
    )


def gained(now: dict[str, set[str]], before: dict[str, set[str]]) -> list[str]:
    """The frozen imports ``now`` holds that ``before`` did not, leaving out those that followed their code."""
    found = []
    for contract, entries in sorted(now.items()):
        old = before.get(contract, set())
        found += [f"{contract}: {entry}" for entry in sorted(entries - old) if not carried(entry, old)]
    return found


def test_every_import_contract_is_kept():
    result = lint_imports()
    assert result.returncode == 0, (
        "An import breaks a contract of [tool.importlinter] in pyproject.toml. Import only from the app itself, base, "
        "live and the apps its LiveAppConfig requires, keep apps out of base, and break a circle between sibling "
        "modules instead of hiding the import inside a function:\n" + result.stdout + result.stderr
    )


def test_each_app_has_the_contract_its_requires_call_for():
    assert app_contract_mismatches(contracts_by_id(current_config()), requires_of_apps()) == []


def test_base_and_the_cycles_keep_their_contracts_and_the_tests_stay_out():
    config = current_config()
    contracts = contracts_by_id(config)
    assert config["root_packages"] == ROOT_PACKAGES
    # Any other setting, like leaving out the imports under TYPE_CHECKING, would take imports out of every contract.
    assert set(config) == {"root_packages", "contracts"}
    base, cycles = base_contract(), cycles_contract()
    for key in ("type", "source_modules", "forbidden_modules", "allow_indirect_imports"):
        assert contracts[BASE_CONTRACT][key] == base[key], key
    assert contracts[CYCLES_CONTRACT]["type"] == cycles["type"]
    assert CYCLE_ANCESTORS <= set(contracts[CYCLES_CONTRACT]["ancestors"])
    for contract in contracts.values():
        assert TESTS_OUT in contract["ignore_imports"], contract["id"]
        # Left at its default, import-linter fails a frozen entry that matches no import any more.
        assert "unmatched_ignore_imports_alerting" not in contract, contract["id"]


def test_the_frozen_imports_never_gain_an_entry():
    text = file_at_base(CONFIG)
    before = importlinter_config(text) if text is not None else None
    if before is None:
        pytest.skip(NO_CONTRACTS_AT_BASE)
    assert gained(frozen(current_config()), frozen(before)) == [], (
        "The frozen imports only shrink: remove the import instead of freezing it."
    )


def test_a_changed_requires_or_a_new_app_without_its_contract_is_reported():
    requires = {"apps.a": ["apps.b"], "apps.b": [], "apps.c": []}
    every_app = sorted(requires)
    contracts = {
        "app-a": app_contract("apps.a", ["apps.b", "apps.c"], every_app),
        "app-b": app_contract("apps.b", [], every_app),
        "app-d": app_contract("apps.d", [], every_app),
    }
    assert app_contract_mismatches(contracts, requires) == [
        'apps.c: no contract; add {"id": "app-c", "name": "apps.c imports only itself, base, live and the apps it '
        'requires", "type": "forbidden", "source_modules": ["apps.c"], "forbidden_modules": ["apps.a", "apps.b", '
        '"config", "control", "shared"], "allow_indirect_imports": true, "ignore_imports": ["**.tests.** -> **"]}',
        "apps.d: a contract for an app that is not installed",
        'apps.a: forbidden_modules is ["config", "control", "shared"], its requires call for ["apps.c", "config", '
        '"control", "shared"]',
    ]


def test_an_entry_new_to_a_contract_is_gained_and_the_tests_exemption_never_is():
    before = {"cycles": {"base.a -> base.b"}}
    now = {"cycles": {"base.a -> base.b", "base.c -> base.d"}, "app-x": set()}
    assert gained(now, before) == ["cycles: base.c -> base.d"]
    config = {"contracts": [{"id": "app-x", "ignore_imports": [TESTS_OUT, "apps.x.api ->  apps.y"]}]}
    assert frozen(config) == {"app-x": {"apps.x.api -> apps.y"}}


def test_a_frozen_import_follows_its_code_into_the_submodules_of_its_modules():
    before = {"cycles": {"base.relay -> base.services", "base.services -> base.middleware"}}
    now = {
        "cycles": {
            "base.relay -> base.services",
            "base.relay -> base.services.relay",
            "base.services.usage -> base.middleware",
        }
    }
    assert gained(now, before) == []


def test_another_module_a_longer_name_or_the_package_above_carries_nothing():
    before = {"cycles": {"base.relay -> base.tenancy.move"}}
    now = {"cycles": {"base.usage -> base.tenancy.move", "base.relay -> base.tenancy.moves", "base.relay -> base.tenancy"}}
    assert gained(now, before) == [
        "cycles: base.relay -> base.tenancy",
        "cycles: base.relay -> base.tenancy.moves",
        "cycles: base.usage -> base.tenancy.move",
    ]


def write_tree(root: Path, files: dict[str, str]) -> None:
    for path, source in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(source, encoding="utf-8")


def toml_config(root_packages: list[str], contracts: list[dict]) -> str:
    lines = ["[tool.importlinter]", f"root_packages = {json.dumps(root_packages)}"]
    for contract in contracts:
        lines += ["", "[[tool.importlinter.contracts]]"]
        lines += [f"{key} = {json.dumps(value)}" for key, value in contract.items()]
    return "\n".join(lines) + "\n"


def test_the_contracts_catch_an_app_outside_its_requires_an_app_in_base_and_a_hidden_circle(tmp_path):
    """The contracts in the shape this test asks of pyproject.toml, on a small tree that breaks each of them."""
    packages = ["apps/__init__.py", "apps/a/__init__.py", "apps/b/__init__.py", "apps/c/__init__.py"]
    packages += ["apps/a/tests/__init__.py", "base/__init__.py", "base/tenancy/__init__.py"]
    packages += [f"{package}/__init__.py" for package in PLATFORM]
    write_tree(tmp_path, dict.fromkeys(packages, ""))
    write_tree(
        tmp_path,
        {
            "apps/a/models.py": "from apps.b import models\n",
            "apps/a/services.py": "def later():\n    from apps.c import models\n",
            "apps/a/tests/test_models.py": "from apps.c import models\nimport control\n",
            "apps/b/models.py": "",
            "apps/c/models.py": "",
            "apps/b/one.py": "from apps.b import two\n",
            "apps/b/two.py": "def later():\n    from apps.b import one\n",
            "base/registry.py": "from apps.a import models\n",
        },
    )
    every_app = ["apps.a", "apps.b", "apps.c"]
    contracts = [app_contract(app, ["apps.b"] if app == "apps.a" else [], every_app) for app in every_app]
    contracts += [base_contract(), cycles_contract() | {"ancestors": ["base", "apps.*"]}]
    (tmp_path / CONFIG).write_text(toml_config(ROOT_PACKAGES, contracts), encoding="utf-8")
    report = lint_imports(cwd=tmp_path).stdout
    assert "apps.a.services -> apps.c.models" in report
    assert "base.registry -> apps.a.models" in report
    assert "No cycles are allowed in apps.b." in report
    assert "apps.a.models -> apps.b.models" not in report
    assert "apps.a.tests" not in report
    assert "Contracts: 2 kept, 3 broken." in report
