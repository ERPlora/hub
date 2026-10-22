"""The public website's CSP: no nonce (its HTML is cached and shared), its own bundle only, never framed; the
editor's preview the same, framed by the hub's own pages."""

from django.utils.csp import CSP

from apps.website.csp import preview_policy, public_policy

PUBLIC = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "object-src": [CSP.NONE],
    "report-uri": ["/csp-report/"],
}


def test_the_public_policy_runs_only_the_hubs_own_scripts_without_a_nonce(settings):
    settings.DEBUG = False
    policy = public_policy()
    assert policy == PUBLIC
    flat = " ".join(value for values in policy.values() for value in values)
    assert CSP.NONCE not in flat and CSP.STRICT_DYNAMIC not in flat and CSP.UNSAFE_EVAL not in flat
    assert "require-trusted-types-for" not in policy


def test_the_preview_is_the_same_page_framed_by_the_hub_itself(settings):
    settings.DEBUG = False
    assert preview_policy() == {**PUBLIC, "frame-ancestors": [CSP.SELF]}


def test_each_call_is_a_fresh_policy(settings):
    settings.DEBUG = False
    public_policy()["script-src"].append("https://evil.example")
    assert public_policy()["script-src"] == [CSP.SELF]


def test_with_debug_the_vite_dev_server_serves_the_bundle(settings):
    settings.DEBUG = True
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "dev_server": "http://localhost:5173"}}
    policy = public_policy()
    for directive in ("script-src", "style-src", "img-src", "font-src", "connect-src"):
        assert "http://localhost:5173" in policy[directive], directive
    assert "ws://localhost:5173" in policy["connect-src"]
    assert preview_policy()["script-src"] == policy["script-src"]
