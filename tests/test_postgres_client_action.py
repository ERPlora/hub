"""Tests of the action .github/actions/postgres-client, the PostgreSQL client every job of the CI that copies a hub's
database installs: pytest's job of test.yml and the e2e stack (.github/actions/e2e-stack) of the smoke and the
nightly. pg_dump refuses a server newer than itself, and the runner's own client is older than the CI's Postgres, so
the client has the major of the Postgres it talks to, which is the Dockerfile's too."""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ACTION = REPO / ".github" / "actions" / "postgres-client" / "action.yml"
E2E_STACK = REPO / ".github" / "actions" / "e2e-stack" / "action.yml"
TEST_WORKFLOW = REPO / ".github" / "workflows" / "test.yml"


@pytest.fixture(scope="module")
def install() -> list[str]:
    action = yaml.safe_load(ACTION.read_text())
    assert action["runs"]["using"] == "composite"
    (step,) = action["runs"]["steps"]
    assert step["shell"] == "bash"
    return step["run"].splitlines()


def the_one(pattern: str, text: str) -> str:
    found = set(re.findall(pattern, text))
    assert len(found) == 1, f"{pattern}: {sorted(found)}"
    return found.pop()


def test_the_client_comes_from_pgdg_signed_with_the_dockerfiles_key_through_apt_install(install):
    assert install[0] == "sudo install -m 644 docker/pgdg.asc /usr/share/keyrings/pgdg.asc"
    assert any("[signed-by=/usr/share/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt" in line
               for line in install)
    installs = [line.split() for line in install if "apt-install.sh" in line]
    assert len(installs) == 1
    assert installs[0][:2] == ["bash", ".github/scripts/apt-install.sh"]
    assert re.fullmatch(r"postgresql-client-\d+", installs[0][3])
    assert not any("apt-get" in line or "apt.postgresql.org.sh" in line for line in install)


def test_its_tools_come_first_in_the_path_of_the_steps_after_it(install):
    major = the_one(r"postgresql-client-(\d+)", "\n".join(install))
    assert install[-1] == f'echo "/usr/lib/postgresql/{major}/bin" >> "$GITHUB_PATH"'


def test_the_client_has_the_major_of_the_dockerfile_and_of_every_postgres_of_the_ci(install):
    major = the_one(r"postgresql-client-(\d+)", "\n".join(install))
    assert the_one(r"postgresql-client-(\d+)", (REPO / "Dockerfile").read_text()) == major
    assert the_one(r"image: pgvector/pgvector:pg(\d+)", E2E_STACK.read_text()) == major
    services = yaml.safe_load(TEST_WORKFLOW.read_text())["jobs"]["python"]["services"]
    assert the_one(r"^postgres:(\d+)$", services["postgres"]["image"]) == major
