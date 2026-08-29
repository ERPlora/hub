#!/usr/bin/env python3
"""Which Rust packages must `cargo test` cover for a given diff.

Usage:  <changed files on stdin> | test-scope.py <cargo-metadata.json> [excluded package…]
Output: three sections on stdout — the mode (`none` | `packages` | `workspace`), one line of
human reason, then one package name per line (only for `packages`).

Same rule as the local pre-push gate (hub#1207), lifted into a file so `test-hub.yml` can run
the packages a PR can reach instead of the whole workspace on every push. Ownership is asked of
`cargo metadata`, never hand-mapped; reverse edges of EVERY kind are followed (a dev-dependency
breaks the dependent's tests, which is precisely what CI runs); anything transversal or
unclaimed widens to the workspace, because the cost of a missed package is a red `develop`.
Contract: scripts/tests/test-scope.test.sh.
"""

import json
import os
import sys

TRANSVERSAL = ("Cargo.lock", "Cargo.toml", "rust-toolchain.toml")
PREFIXES = (".cargo/", "schemas/")


def verdict(mode, reason, pkgs=()):
    print(mode)
    print(reason)
    for name in sorted(pkgs):
        print(name)
    raise SystemExit(0)


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(
            "usage: test-scope.py <cargo-metadata.json> [excluded package…] < changed-files\n"
        )
        raise SystemExit(64)
    with open(sys.argv[1], encoding="utf-8") as fh:
        meta = json.load(fh)
    excludes = set(sys.argv[2:])
    rust_dirs = set(
        d for d in os.environ.get("HUB_GATE_RUST_DIRS", "crates").split() if d
    )
    root = meta["workspace_root"]
    members = set(meta.get("workspace_members") or [])

    # name -> directory that owns it, relative to the workspace root
    pkgs = {}
    for p in meta["packages"]:
        if members and p["id"] not in members:
            continue
        rel = os.path.relpath(os.path.dirname(p["manifest_path"]), root)
        pkgs[p["name"]] = "" if rel == "." else rel
    names = set(pkgs)

    rdeps = {n: set() for n in names}
    for p in meta["packages"]:
        if p["name"] not in names:
            continue
        for d in p["dependencies"]:
            if d["name"] in names and d["name"] != p["name"]:
                rdeps[d["name"]].add(p["name"])

    touched = set()
    for path in [
        line.strip() for line in sys.stdin.read().splitlines() if line.strip()
    ]:
        if path in TRANSVERSAL or path.startswith(PREFIXES):
            verdict("workspace", "%s can change what every crate compiles" % path)
        owner, best = None, -1
        for name, rel in pkgs.items():
            if rel and (path == rel or path.startswith(rel + "/")) and len(rel) > best:
                owner, best = name, len(rel)
        if owner is not None:
            touched.add(owner)
        elif path.split("/")[0] in rust_dirs:
            verdict("workspace", "%s sits in Rust source that no package claims" % path)

    scope, stack = set(), list(touched)
    while stack:
        n = stack.pop()
        if n in scope:
            continue
        scope.add(n)
        stack.extend(rdeps.get(n, ()))
    scope -= excludes
    testable = names - excludes

    if not scope:
        verdict("none", "no Rust package is touched by this diff")
    if testable and scope >= testable:
        verdict("workspace", "the diff reaches every testable package")
    verdict(
        "packages",
        "%d of %d packages reachable from this diff" % (len(scope), len(testable)),
        scope,
    )


if __name__ == "__main__":
    main()
