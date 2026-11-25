"""Tests of scripts/nightly_stack.py: what one night does, from fetching main to cleaning up its stack.

The nights run as GitHub Actions or a person runs them, with the doubles of tests/nightly_doubles.py: real git, fake tools.
"""

import os
import re
import signal
import subprocess
import time

import pytest
from nightly_doubles import NOTHING_RUNS, World, alive, fresh_world, git, nightly_stack, wait_for


@pytest.fixture
def world(tmp_path):
    yield from fresh_world(tmp_path)


@pytest.fixture(scope="module")
def red(tmp_path_factory):
    """One red night, the clones' first: what it did is read by several tests."""
    made = World(tmp_path_factory.mktemp("red"))
    made.night()
    yield made
    made.stop()


# --- a red night --------------------------------------------------------------------------------------------------
def test_a_red_night_runs_every_spec_once_on_the_newest_main_fetched_that_night(red):
    assert red.status == 1
    assert red.calls_re(r"^e2e hub ") == 1
    assert red.calls(f"HEAD={red.newest_main}") == 1
    assert git("-C", str(red.hub), "rev-parse", "HEAD") == red.clone_head
    assert red.calls_re(r"^e2e hub args=--global-timeout=21600000 HEAD=") == 1


def test_the_specs_run_on_the_nights_own_stack(red):
    assert red.calls("E2E_HUB_PORT=9770 VITE_DEV_PORT=9775 SAAS_URL=http://localhost:9771 DB_NAME=hub_e2e_9770"
                     " E2E_SAAS_DB=saas_e2e_9771") == 1
    assert red.calls(f"E2E_SAAS_DIR={red.nightly}/saas E2E_MAIL_DIR={red.nightly}/saas/.mail-9771 CI=1") == 1
    assert red.calls(f"COMPOSE_FILE={red.erplora}/compose.yaml CATALOG_DIR={red.erplora}/blueprints/img") == 1
    assert red.calls_re(f"E2E_OUTPUT_DIR={re.escape(str(red.nightly))}/runs/[0-9-]+/test-results$") == 1
    assert red.calls("e2e sees .env LOCAL_SETTING=hub") == 1
    assert red.calls("e2e sees a server alive") == 2


def test_the_databases_are_made_and_the_saas_seeded_before_the_servers_start(red):
    assert red.calls("database hub DB_NAME=hub_e2e_9770 E2E_SAAS_PORT=") == 1
    assert red.calls("database saas DB_NAME= E2E_SAAS_PORT=9771") == 1
    assert red.calls("seed saas tests/e2e/panel/whatsapp_hub_seed.py 0190-a 0190-b DB_NAME=saas_e2e_9771"
                     " HUB_INTERNAL_URL=http://127.0.0.1:9770") == 1
    assert red.calls_re(r"^docker .* -d hub_e2e_9770 .*select id from base_hub") == 1
    assert red.calls("seed saas tests/e2e/panel/assistant_seed.py gateway http://127.0.0.1:9772/v1"
                     " DB_NAME=saas_e2e_9771") == 1
    assert red.calls("manage saas seed_taxonomy DB_NAME=saas_e2e_9771") == 1
    assert red.first("database saas") < red.first("manage saas seed_taxonomy") < red.first("runserver")


def test_the_servers_run_as_the_e2e_readme_says_and_are_waited_for(red):
    assert red.calls(
        f"runserver saas 127.0.0.1:9771 DB_NAME=saas_e2e_9771 VITE_DEV_PORT=9776 SAAS_URL="
        f" HUB_INTERNAL_URL=http://localhost:9770 EMAIL_FILE_PATH={red.nightly}/saas/.mail-9771"
        " ASSISTANT_SERVICE_PROVIDER=e2e-local E2E_RELAX_LOGIN_RATE_LIMIT=True DEMO_SPAWN_RATELIMIT=100/h"
        " HUB_CALLBACK_TEMPLATE=http://{slug}.localhost:9770/auth/callback"
        " HUB_ADMIN_CALLBACK_URL=http://hubs.localhost:9770/auth/callback HTTPS_PROXY=http://127.0.0.1:9779"
        " OPENAI_API_KEY=sk-e2e-0000000000000000000000000000e2e1") == 1
    assert red.calls("runserver hub 127.0.0.1:9770 DB_NAME=hub_e2e_9770 VITE_DEV_PORT=9775"
                     " SAAS_URL=http://localhost:9771") == 1
    assert red.calls_re(f"^runserver hub .*CATALOG_DIR={re.escape(str(red.erplora))}/blueprints/img$") == 1
    assert red.calls_re(r"^curl -fsS -o /dev/null --max-time 5 ") == 3
    assert red.first("curl") < red.first("e2e hub")


def test_the_night_fetches_both_repositories_and_makes_worktrees_of_its_own(red):
    assert red.calls(f"git -C {red.hub} fetch --quiet origin") == 1
    assert red.calls(f"git -C {red.saas} fetch --quiet origin") == 1
    for repo, name in ((red.hub, "hub"), (red.saas, "saas")):
        assert red.calls(f"git -C {repo} worktree add --quiet --detach {red.nightly}/{name} origin/main") == 1
        assert red.calls(f"git -C {red.nightly}/{name} submodule update --init --quiet") == 1
        assert red.calls(f"git -C {repo} worktree remove --force {red.nightly}/{name}") == 1
        assert red.calls(f"git -C {repo} worktree prune") == 2


def test_the_night_cleans_up_before_and_after_itself(red):
    assert red.calls_re(r"^drop (hub DB_NAME=hub_e2e_9770|saas DB_NAME= E2E_SAAS_PORT=9771)") == 4
    assert red.first("drop saas") < red.first("database hub")
    assert red.last("drop saas") > red.first("e2e hub")
    assert red.alive_servers() == 0
    assert not (red.nightly / "hub").exists()
    assert not (red.nightly / "saas").exists()
    assert red.worktrees() == (1, 1)
    assert not (red.nightly / "lock").exists()


def test_a_red_night_lists_what_came_out_red_in_its_log_and_writes_no_issue(red):
    log = red.log()
    assert len(red.night_logs()) == 1
    assert "Pruebas de navegador del Hub: en rojo" in log
    assert "`sale-sales.spec.ts:4` › charges in cash" in log
    assert f"commit `{red.newest_main[:7]}`" in log
    assert re.search(r"`~/\.erplora/hub-nightly-e2e/runs/[0-9-]+`", log)
    assert "Sin publicar: no se escribe ninguna issue." in log
    assert red.read("gh") == ""
    assert red.out() == ""


def test_a_report_that_cannot_be_read_through_turns_the_night_red(world):
    (world.root / "array.json").write_text("[]")
    assert world.night(FAKE_E2E_EXIT="0", FAKE_RESULTS=str(world.root / "array.json")) == 1
    assert "the report failed: what came out red is not listed" in world.log()
    assert "night over: success" in world.log()


# --- a night that never reaches the specs -------------------------------------------------------------------------
@pytest.mark.parametrize(("settings", "step"), [
    ({"FAKE_DB_FAILS": "saas"}, "la BD del SaaS"),
    ({"FAKE_DB_FAILS": "hub"}, "la BD del Hub"),
    ({"FAKE_MANAGE_EXIT": "1"}, "la siembra del SaaS"),
    ({"FAKE_SEED_EXIT": "1"}, "la siembra del SaaS"),
    ({"FAKE_IDS": "0190-a"}, "la siembra del SaaS"),
    ({"FAKE_SYNC_EXIT": "1"}, "las dependencias del Hub"),
    ({"FAKE_DROP_FAILS": "saas"}, "borrar lo que dejó una noche anterior"),
    ({"NIGHTLY_HUB_REF": "no-such-commit"}, "los worktrees"),
    ({"FAKE_CURL_EXIT": "7", "NIGHTLY_START_SECONDS": "1"}, "arrancar los servidores"),
    ({"FAKE_SERVER_EXITS": "1", "FAKE_CURL_EXIT": "7"}, "arrancar los servidores"),
])
def test_a_step_before_the_specs_that_fails_is_a_red_night_naming_it(world, settings, step):
    assert world.night(**settings) == 1
    assert world.calls_re(r"^e2e ") == 0
    assert f"La pasada no llegó a las specs: falló «{step}»." in world.log()
    assert world.alive_servers() == 0
    assert world.worktrees() == (1, 1)


def test_a_failed_step_still_drops_the_databases_it_made(world):
    world.night(FAKE_DB_FAILS="saas")
    assert world.calls_re(r"^runserver ") == 0
    assert world.last("drop hub") > world.first("database saas")


def test_the_seeding_needs_exactly_the_ids_of_a_and_b(world):
    world.night(FAKE_IDS="0190-a")
    assert "the Hub's database should hold a and b, and holds «0190-a»" in world.night_logs()[0].read_text()
    assert world.calls_re(r"^seed ") == 0


def test_servers_that_never_answer_are_said_in_the_log(world):
    world.night(FAKE_CURL_EXIT="7", NIGHTLY_START_SECONDS="1")
    assert world.calls_re(r"^curl ") >= 2
    assert "the servers did not answer within 1 s" in world.night_logs()[0].read_text()


def test_a_server_that_exits_before_answering_is_said_in_the_log(world):
    world.night(FAKE_SERVER_EXITS="1", FAKE_CURL_EXIT="7")
    assert "a server exited before answering: see hub.log and saas.log" in world.night_logs()[0].read_text()


def test_a_night_that_cannot_fetch_main_is_red(world):
    git("-C", str(world.hub), "remote", "set-url", "origin", str(world.root / "gone"))
    assert world.night() == 1
    assert "falló «traer origin/main»" in world.log()
    assert world.calls_re(NOTHING_RUNS) == 0
    assert "could not drop" not in world.night_logs()[0].read_text()


def test_a_night_without_any_commit_names_it_unknown(world):
    git("-C", str(world.hub), "remote", "set-url", "origin", str(world.root / "gone"))
    git("-C", str(world.hub), "update-ref", "-d", "refs/remotes/origin/main")
    assert world.night() == 1
    assert "commit `unknown`" in world.log()


def test_a_worktree_that_cannot_be_pruned_is_a_red_night_and_is_said(world):
    assert world.night(FAKE_PRUNE_EXIT="1") == 1
    assert "falló «los worktrees»" in world.log()
    assert f"could not remove {world.nightly}/hub" in world.night_logs()[0].read_text()


def test_a_folder_left_where_a_worktree_goes_is_replaced(world):
    (world.nightly / "hub").mkdir(parents=True)
    (world.nightly / "hub" / "half-written").write_text("cut\n")
    assert world.green() == 0
    assert world.calls_re(r"^e2e hub ") == 1
    assert not (world.nightly / "hub").exists()


def test_a_checkout_without_env_still_gets_its_worktree(world):
    (world.saas / ".env").unlink()
    assert world.green() == 0
    assert world.calls("e2e sees .env LOCAL_SETTING=hub") == 1


def test_a_hub_database_that_cannot_be_read_stops_the_seeding(world):
    assert world.night(FAKE_DOCKER_EXIT="1") == 1
    assert "falló «la siembra del SaaS»" in world.log()
    assert "should hold a and b" not in world.night_logs()[0].read_text()


def test_a_database_that_cannot_be_dropped_is_said_and_left_to_the_next_night(world):
    world.night(FAKE_DROP_FAILS="hub")
    log = world.night_logs()[0].read_text()
    assert "falló «borrar lo que dejó una noche anterior»" in world.log()
    assert "could not drop hub_e2e_9770: the next night tries again" in log
    assert world.worktrees() == (1, 1)


def test_without_meta_s_proxy_the_saas_still_starts(world):
    assert world.green(FAKE_GRAPH_EXIT="1") == 0
    assert world.calls_re(r"^runserver saas .* HTTPS_PROXY= OPENAI_API_KEY=") == 1
    assert "whatsapp-graph.ts failed" in world.night_logs()[0].read_text()


def test_servers_that_ignore_term_are_killed_after_20_seconds(world):
    started = time.monotonic()
    assert world.green(FAKE_SERVER_KEEPS_TERM="1") == 0
    assert time.monotonic() - started >= 20
    assert "still running after 20 s: killing it" in world.night_logs()[0].read_text()
    assert world.alive_servers() == 0


def test_what_listens_on_the_stacks_ports_is_stopped_with_its_group_never_the_nights(world):
    listeners, children = world.root / "listeners", world.root / "children"
    # A runserver a spec restarted, with its Vite, in a group of its own; and one in the night's own group, which has to
    # be stopped alone. Both orphans, so that whoever reaps them is not this test.
    subprocess.run(["bash", "-c", f"sleep 60 & echo $! >> {listeners}"], check=True)
    subprocess.run(["bash", "-c", f"setsid bash -c 'sleep 60 & echo $! >> {children}; echo $$ >> {listeners};"
                    " exec sleep 60' &"], check=True)
    wait_for(lambda: len(listeners.read_text().split()) == 2 and children.exists())
    pids = [int(pid) for pid in listeners.read_text().split() + children.read_text().split()]
    world.every_pid += pids
    assert world.green(FAKE_LISTENERS=str(listeners)) == 0
    wait_for(lambda: not any(alive(pid) for pid in pids), 5)
    assert [pid for pid in pids if alive(pid)] == []


def test_nightly_hub_port_moves_the_stack_and_spec_runs_only_that_spec(world):
    assert world.green("--spec", "tests/e2e/sale-sales.spec.ts", NIGHTLY_HUB_PORT="28770") == 0
    assert world.calls("E2E_HUB_PORT=28770 VITE_DEV_PORT=28775 SAAS_URL=http://localhost:28771 DB_NAME=hub_e2e_28770"
                       " E2E_SAAS_DB=saas_e2e_28771") == 1
    assert world.calls_re(r"^runserver saas 127\.0\.0\.1:28771 DB_NAME=saas_e2e_28771 VITE_DEV_PORT=28776 ") == 1
    assert world.calls_re(r"^e2e hub args=--global-timeout=[0-9]+ tests/e2e/sale-sales\.spec\.ts HEAD=") == 1
    assert world.calls_re(r"^lsof -nP -t -sTCP:LISTEN -iTCP:28770 -iTCP:28771 -iTCP:28772 -iTCP:28775 -iTCP:28776"
                          r" -iTCP:28779$") > 0


def test_grep_and_a_commit_not_pushed_run_only_those_tests_on_that_commit(world):
    tree = git("-C", str(world.hub), "rev-parse", f"{world.clone_head}^{{tree}}")
    unpushed = git("-C", str(world.hub), "commit-tree", "-p", world.clone_head, "-m", "unpushed", tree)
    assert world.green(NIGHTLY_GREP="@smoke", NIGHTLY_HUB_REF=unpushed, NIGHTLY_MAX_MINUTES="20") == 0
    assert world.calls_re(r"^e2e hub args=--global-timeout=1200000 --grep @smoke HEAD=") == 1
    assert world.calls(f"HEAD={unpushed} ") == 1
    assert git("-C", str(world.hub), "rev-parse", "HEAD") == world.clone_head


def test_shard_runs_only_that_share_of_the_specs(world):
    assert world.green("--shard", "3/8", "--spec", "tests/e2e/sale-sales.spec.ts") == 0
    assert world.calls_re(r"^e2e hub args=--global-timeout=[0-9]+ --shard=3/8 tests/e2e/sale-sales\.spec\.ts HEAD=") == 1


def test_the_specs_that_spend_real_tokens_stay_off(world):
    world.night(QA_REAL_PROVIDER="1", E2E_HEADED="1", DB_NAME="hub")
    assert world.calls_re(r"QA_REAL_PROVIDER= E2E_OUTPUT_DIR=") == 1
    assert world.calls("database saas DB_NAME= E2E_SAAS_PORT=9771") == 1


def test_the_report_names_the_commit_the_specs_ran_on_when_main_moves_meanwhile(world):
    world.night(FAKE_MAIN_MOVES=str(world.root / "remote" / "hub"))
    assert git("-C", str(world.hub), "rev-parse", "origin/main") != world.newest_main
    assert f"commit `{world.newest_main[:7]}`" in world.log()


def test_a_server_already_gone_when_the_clean_up_stops_it_keeps_the_night_green(world):
    gone = subprocess.Popen(["true"])
    gone.wait()
    (world.root / "gone.pid").write_text(f"{gone.pid}\n")
    assert world.green(FAKE_GONE_LISTENER=str(world.root / "gone")) == 0
    assert world.last("drop saas") > world.first("e2e hub")
    assert world.worktrees() == (1, 1)


# --- a night that is told to stop ---------------------------------------------------------------------------------
def test_a_night_told_to_stop_while_the_specs_run_ends_without_waiting_for_them(world):
    night = world.start(FAKE_E2E_NEVER_ENDS="1")
    wait_for(lambda: len(world.pids()) >= 3)
    os.kill(int((world.nightly / "lock" / "pid").read_text()), signal.SIGTERM)
    assert night.wait(timeout=60) == 143
    world.every_pid += world.pids()
    assert len(world.pids()) == 3
    assert world.alive_servers() == 0
    assert world.last("drop saas") > world.first("e2e hub")
    assert world.worktrees() == (1, 1)
    assert not (world.nightly / "lock").exists()


def test_a_night_told_to_stop_during_a_command_stops_once_it_ends(world):
    night = world.start(FAKE_DB_SECONDS="2")
    wait_for(lambda: world.calls("database hub") > 0)
    os.kill(int((world.nightly / "lock" / "pid").read_text()), signal.SIGTERM)
    assert night.wait(timeout=60) == 143
    assert world.calls("database saas") == 0
    assert world.worktrees() == (1, 1)


def test_a_night_told_to_stop_while_it_waits_for_the_servers_asks_them_no_more(world):
    night = world.start(FAKE_CURL_EXIT="7", NIGHTLY_START_SECONDS="60")
    wait_for(lambda: world.calls("curl ") > 0)
    time.sleep(0.5)
    os.kill(int((world.nightly / "lock" / "pid").read_text()), signal.SIGTERM)
    assert night.wait(timeout=60) == 143
    world.every_pid += world.pids()
    assert world.calls("curl ") == 1
    assert world.alive_servers() == 0


def test_a_night_told_to_stop_during_a_step_stops_once_that_step_ends(world):
    night = world.start(FAKE_SYNC_SECONDS="2")
    wait_for(lambda: world.calls("uv hub sync") > 0)
    os.kill(int((world.nightly / "lock" / "pid").read_text()), signal.SIGINT)
    assert night.wait(timeout=60) == 130
    assert world.calls("uv hub sync done") == 1
    assert world.calls("pnpm hub install") == 1
    assert world.calls("uv saas sync") == 0
    assert world.worktrees() == (1, 1)
    assert not (world.nightly / "lock").exists()



def test_the_proxy_settings_are_the_var_value_words_printed():
    assert nightly_stack.assignments("HTTPS_PROXY=http://127.0.0.1:9779 NO_PROXY=a=b\n") == {
        "HTTPS_PROXY": "http://127.0.0.1:9779", "NO_PROXY": "a=b"}


def test_a_command_that_cannot_start_is_said_and_fails(capsys, tmp_path):
    assert nightly_stack.run(["no-such-command-anywhere"]).returncode == 127
    folder = str(tmp_path)
    settings = nightly_stack.Settings(folder, folder, folder, folder, 9770, 1, 1, 1, "ERPlora/hub")
    night = nightly_stack.Night(settings, folder, [])
    assert night.start(["no-such-command-anywhere"], folder, {}) is None
    assert night.started == []
    assert capsys.readouterr().err.count("nightly-e2e: [Errno 2] No such file or directory") == 2
