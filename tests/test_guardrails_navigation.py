"""Guardrail of the screens: every screen of an app opens under an entry of its own menu.

A screen takes the permission of the entry of its app's menu (``navigation`` in ``apps.py``, each ``Nav`` with the
``permission`` that opens it) whose ``path`` is its longest prefix: a screen under no entry would have no permission to
open with. So every route with a session of a module's ``frontend/routes.ts`` lies under one of its entries, and every
entry leads to a screen of its app. What is not a screen of the app is left out: a route without a session (the public
pages a customer opens), a background piece (``meta.background``, which the shell mounts beside every screen), a
redirect, and what only the development server registers (``import.meta.env.DEV``).
"""

import re
from pathlib import Path

import pytest
from live.meta import module_configs

#: One route object of a ``routes.ts``: its path and the rest of the object, one level of braces deep (its ``meta``).
ROUTE = re.compile(r"\{\s*path:\s*'(?P<path>[^']+)'(?P<body>(?:[^{}]|\{[^{}]*\})*)\}")
#: The routes only the development server registers: ``...(import.meta.env.DEV ? [ … ] : [])``.
DEV_ONLY = re.compile(r"\.\.\.\(\s*import\.meta\.env\.DEV\s*\?\s*\[[^\[\]]*\]\s*:\s*\[\]\s*\)")
SESSION = re.compile(r"\bauth:\s*true\b")
BACKGROUND = re.compile(r"\bbackground:\s*true\b")
REDIRECT = re.compile(r"\bredirect:")


def screens(routes_ts: str) -> list[str]:
    """The paths of the screens with a session a ``routes.ts`` declares, in its order."""
    shipped = DEV_ONLY.sub("", routes_ts)
    return [
        match["path"]
        for match in ROUTE.finditer(shipped)
        if SESSION.search(match["body"]) and not BACKGROUND.search(match["body"]) and not REDIRECT.search(match["body"])
    ]


def under(path: str, entry: str) -> bool:
    return path == entry or path.startswith(f"{entry.rstrip('/')}/")


def strays(routes_ts: str, entries: list[str]) -> list[str]:
    """The screens of ``routes_ts`` under none of ``entries``."""
    return [path for path in screens(routes_ts) if not any(under(path, entry) for entry in entries)]


def routed_modules() -> list:
    return [config for config in module_configs() if (Path(config.path) / "frontend" / "routes.ts").is_file()]


def routes_of(config) -> str:
    return (Path(config.path) / "frontend" / "routes.ts").read_text(encoding="utf-8")


@pytest.mark.parametrize("config", routed_modules(), ids=lambda config: config.label)
def test_every_screen_of_an_app_is_under_an_entry_of_its_menu(config):
    assert strays(routes_of(config), [nav.path for nav in config.navigation]) == []


@pytest.mark.parametrize("config", routed_modules(), ids=lambda config: config.label)
def test_every_entry_of_an_app_s_menu_leads_to_one_of_its_screens(config):
    """Also what keeps the reading of ``routes.ts`` honest: a parser that found no screen would fail here."""
    assert [nav.path for nav in config.navigation if nav.path not in screens(routes_of(config))] == []


MADE_UP = """
const routes: RouteRecordRaw[] = [
  { path: '/stock', redirect: '/stock/items', meta: { auth: true } },
  { path: '/stock/items', component: () => import('./pages/ItemsPage.vue'), meta: { auth: true } },
  {
    path: '/stock/items/:id',
    component: () => import('./pages/ItemPage.vue'),
    props: true,
    meta: { auth: true },
  },
  { path: '/stock/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
  { path: '/stock-guide', component: () => import('./pages/GuidePage.vue'), meta: { auth: true } },
  { path: '/stock/host', component: () => import('./components/Host.vue'), meta: { auth: true, background: true } },
  { path: '/p/:slug/stock', component: () => import('./pages/PublicPage.vue'), meta: { auth: false, chrome: false } },
  ...(import.meta.env.DEV
    ? [
        {
          path: '/stock/preview',
          component: () => import('./pages/PreviewPage.vue'),
          meta: { auth: true },
        },
      ]
    : []),
];
"""


def test_the_screens_of_a_routes_file_are_those_with_a_session_that_ship():
    assert screens(MADE_UP) == ["/stock/items", "/stock/items/:id", "/stock/settings", "/stock-guide"]


def test_a_screen_under_no_entry_is_caught():
    """The settings without an entry, and a path that only shares the entry's letters, are strays."""
    assert strays(MADE_UP, ["/stock/items"]) == ["/stock/settings", "/stock-guide"]
    assert strays(MADE_UP, ["/stock/items", "/stock/settings", "/stock-guide"]) == []
