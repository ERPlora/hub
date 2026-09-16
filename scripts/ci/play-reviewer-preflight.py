#!/usr/bin/env python3
"""Does the Google review account really get inside a living business? — ERPlora/hub#1718.

The step a person runs BEFORE sending the app to Google (`apps/tauri/GOOGLE-PLAY.md`). The
instructions handed to the reviewer promise that signing in with the test account shows the app
working; on 2026-09-09 that was measured and it was false — the account landed on the empty «Crea
tu negocio gratis» screen, and once a hub existed, on a hub with zero modules installed. A reviewer
who cannot see the app rejects it, and a rejection costs another whole round.

Usage:  python3 scripts/ci/play-reviewer-preflight.py
Exits 0 only when ALL of it holds, and 1 naming the first thing that does not:

  missing_credentials  the `.env` does not carry the reviewer account   → never a silent skip
  saas_unreachable     the SaaS did not answer
  login_rejected       the account no longer signs in
  hubs_unreadable      the SaaS would not list the account's hubs
  no_hubs              the account has no business at all               → the 09/09 signup screen
  hub_not_in_account   PLAY_REVIEWER_HUB names a hub that is not one of the account's
  hub_unreachable      that hub's address does not answer
  hub_not_ready        it answers, but it is not `status: UP`
  hub_without_modules  it is up and EMPTY                               → the 09/09 shell

The slug is never written here: it comes from `PLAY_REVIEWER_HUB`. A hardcoded one would keep
passing after the `.env` is pointed elsewhere, which is exactly how `PLAY_REVIEWER_HUB=salon-aurora`
survived while that address answered 404.

The password is read and sent, never printed — not even on the failure paths.

Contract test: `scripts/tests/play-reviewer-preflight.test.sh` (hermetic, fake SaaS and fake hub).
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

# 🪤 Measured 2026-09-16: with urllib's default User-Agent, Cloudflare answers the SaaS with
# 403 «error code: 1010» and the control would die at the login without looking at anything.
USER_AGENT = "ERPlora-play-reviewer-preflight/1.0 (+https://erplora.com)"

SAAS_URL = os.environ.get("PLAY_REVIEWER_SAAS_URL", "https://erplora.com").rstrip("/")
# `{slug}` is filled from PLAY_REVIEWER_HUB. Hubs are served per-tenant under this domain.
HUB_URL = os.environ.get("PLAY_REVIEWER_HUB_URL", "https://{slug}.a.erplora.com")

TIMEOUT = 30

REQUIRED = ("PLAY_REVIEWER_EMAIL", "PLAY_REVIEWER_PASSWORD", "PLAY_REVIEWER_HUB")


def fail(code: str, message: str) -> None:
    """A red that names what to do. A red that does not is one somebody 'fixes' by deleting it."""
    print(f"FAIL {code}: {message}", file=sys.stderr)
    sys.exit(1)


def default_env_file() -> str:
    """The monorepo's root `.env` — the parent of this repo, where `PLAY_REVIEWER_*` lives."""
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(os.path.dirname(repo_root), ".env")


def read_env_file(path: str) -> dict:
    """`KEY=value` pairs, quotes stripped. A missing file is not an error here: the caller decides,
    because the variables may perfectly well come from the environment instead."""
    values = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = re.match(
                    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line
                )
                if not match:
                    continue
                value = match.group(2).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values[match.group(1)] = value
    except OSError:
        return {}
    return values


def credentials() -> tuple[str, str, str]:
    """The environment wins over the file, so a caller can point this at another account without
    editing the `.env`. Missing configuration is LOUD: naming the variables is what stops the
    next person from working around the control instead of setting it up."""
    env_file = os.environ.get("PLAY_REVIEWER_ENV_FILE") or default_env_file()
    from_file = read_env_file(env_file)
    values = {
        key: (os.environ.get(key) or from_file.get(key) or "").strip()
        for key in REQUIRED
    }
    missing = [key for key in REQUIRED if not values[key]]
    if missing:
        fail(
            "missing_credentials",
            f"falta {', '.join(missing)}. Ponlas en {env_file} (o expórtalas) con la cuenta con "
            "la que Google revisa la app y el slug de su hub. Sin ellas esto NO se puede "
            "comprobar, y enviar la app a Google a ciegas es lo que costó la ronda del 09/09.",
        )
    return (
        values["PLAY_REVIEWER_EMAIL"],
        values["PLAY_REVIEWER_PASSWORD"],
        values["PLAY_REVIEWER_HUB"],
    )


def request(
    url: str, *, data: dict | None = None, token: str | None = None
) -> tuple[int, str]:
    """`(status, body)`. An HTTP error is an answer, not a crash — the verdict reads its code."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc.reason if isinstance(exc, urllib.error.URLError) else exc)


def as_json(raw: str) -> object:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def main() -> None:
    email, password, wanted_slug = credentials()

    # ── 1. The account signs in ──────────────────────────────────────────────
    status, raw = request(
        f"{SAAS_URL}/api/v1/auth/login/", data={"email": email, "password": password}
    )
    if status == 0:
        fail("saas_unreachable", f"{SAAS_URL} no contesta: {raw}")
    if status != 200:
        fail(
            "login_rejected",
            f"la cuenta de revisión ya no entra en {SAAS_URL} (HTTP {status}). Google usa "
            "exactamente estas credenciales: si no entran, el revisor tampoco.",
        )
    payload = as_json(raw)
    token = payload.get("access") if isinstance(payload, dict) else None
    if not token:
        fail(
            "login_rejected",
            "el SaaS contestó 200 al login pero sin `access`: no hay sesión con la que seguir",
        )

    # ── 2. …and has a business ───────────────────────────────────────────────
    status, raw = request(f"{SAAS_URL}/api/v1/hubs/", token=token)
    if status == 0:
        fail(
            "saas_unreachable",
            f"{SAAS_URL} dejó de contestar al listar los hubs: {raw}",
        )
    if status != 200:
        fail(
            "hubs_unreadable", f"el SaaS no lista los hubs de la cuenta (HTTP {status})"
        )
    payload = as_json(raw)
    hubs = payload.get("hubs") if isinstance(payload, dict) else None
    if not isinstance(hubs, list):
        fail("hubs_unreadable", "la respuesta del SaaS no trae la lista `hubs`")
    slugs = [h.get("slug") for h in hubs if isinstance(h, dict) and h.get("slug")]
    if not slugs:
        fail(
            "no_hubs",
            "la cuenta de revisión no tiene NINGÚN negocio: quien entre verá la pantalla de alta "
            "«Crea tu negocio gratis», que es justo lo que vio el revisor el 09/09.",
        )

    # ── 3. …and it is the one the `.env` names ───────────────────────────────
    if wanted_slug not in slugs:
        fail(
            "hub_not_in_account",
            f"PLAY_REVIEWER_HUB={wanted_slug} no es un hub de la cuenta de revisión. "
            f"Los suyos son: {', '.join(sorted(slugs))}. Corrige la variable al que toque "
            "(mandar al revisor a una dirección que no es suya es un 404 garantizado).",
        )

    # ── 4. …that is actually up ──────────────────────────────────────────────
    hub_url = HUB_URL.replace("{slug}", wanted_slug).rstrip("/")
    status, raw = request(f"{hub_url}/readyz")
    if status == 0:
        fail("hub_unreachable", f"{hub_url}/readyz no contesta: {raw}")
    if status != 200:
        fail(
            "hub_not_ready",
            f"{hub_url}/readyz contesta HTTP {status}: el revisor no vería la app",
        )
    ready = as_json(raw)
    if not isinstance(ready, dict):
        fail("hub_not_ready", f"{hub_url}/readyz no devolvió un documento JSON")
    if ready.get("status") != "UP":
        fail(
            "hub_not_ready",
            f"{hub_url}/readyz contesta 200 pero se declara `{ready.get('status')}`. "
            "El 200 no es el veredicto: lo es el `status` de dentro.",
        )

    # ── 5. …and is not an empty shell. This is the 09/09 failure ─────────────
    modules = (
        ready.get("checks", {}).get("modules", {})
        if isinstance(ready.get("checks"), dict)
        else {}
    )
    registered = modules.get("registered") if isinstance(modules, dict) else None
    if not isinstance(registered, int) or registered <= 0:
        fail(
            "hub_without_modules",
            f"el hub {wanted_slug} está vivo pero con {registered if registered is not None else 'ningún'} "
            "módulo registrado: el revisor entra y ve «Aquí aparecerán tus apps», sin TPV, sin "
            "agenda y sin caja. Aplica una plantilla de sector antes de enviar.",
        )

    print(
        f"OK: la cuenta de revisión entra, su hub `{wanted_slug}` responde UP "
        f"(versión {ready.get('version', '?')}) y tiene {registered} módulos registrados."
    )


if __name__ == "__main__":
    main()
