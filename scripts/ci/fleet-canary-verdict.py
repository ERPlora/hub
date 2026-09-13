#!/usr/bin/env python3
"""The canary verdict about ONE digest — what the `fleet-canary` job of `build-hub.yml` acts on.

Usage: fleet-canary-verdict.py <release.json> <digest>
Prints `<verdict>\t<detail>` and exits 0 whatever the verdict (a verdict is data, not a crash):

  verified     the canary approved this digest                      → the job goes green
  pending      no verdict yet                                       → keep polling
  unknown      the body could not be read (a 502 page, a timeout)   → keep polling
  quarantined  the canary vetoed this digest                        → red
  refused      the SaaS would not run the canary                    → red, at once
  errored      the canary could not run to the end                  → red, at once
  failed       the canary ran and the image failed                  → red, at once
  moved        the pointer no longer serves this digest             → red
  missing      the SaaS has no release for this digest              → red
  mismatch     the SaaS answered about another digest               → red

hub#1790: the job used to read `current`, which after a veto is ANOTHER release. On 2026-09-11 the
canary failed on `v1.1.22`, the pointer fell back to 1.1.19, and the job printed «the canary
approved» over the veto. The verdict is therefore always decided about the job's own digest:

* a SaaS that answers `?image=` carries `release` — this digest's release — and its `canary_state`;
* a SaaS that does not (no `release` key) only has `current`, which speaks for this digest only
  while it IS this digest; the pointer moving away from it is a red, never somebody else's verdict.
"""

import json
import sys

WAITING = {"pending", "running", ""}
RED_AT_ONCE = {"refused", "errored", "failed"}


def sha(image: str) -> str:
    """`sha256:…` of an image reference, lower-cased: the job spells the owner `ERPlora` and the
    SaaS stores it lower-cased, and both are the same image."""
    image = (image or "").strip()
    return image.rsplit("@", 1)[-1].lower() if "@" in image else image.lower()


def verdict(body: object, digest: str) -> tuple[str, str]:
    if not isinstance(body, dict):
        return "unknown", "the SaaS answered something that is not the release document"
    want = sha(digest)

    if "release" in body:
        release = body["release"]
        if not isinstance(release, dict):
            return "missing", f"the SaaS has no release for {digest}"
        if sha(release.get("image", "")) != want:
            return (
                "mismatch",
                f"asked about {digest}, the SaaS answered about {release.get('image')}",
            )
        state = str(release.get("canary_state") or "")
        if state == "verified":
            return "verified", str(
                release.get("canary_version_seen") or release.get("version") or ""
            )
        if state == "quarantined":
            return "quarantined", str(
                release.get("quarantine_reason") or "no reason recorded"
            )
        if state in RED_AT_ONCE:
            reason = release.get("canary_run_reason") or release.get(
                "canary_refused_reason"
            )
            return state, str(reason or "no reason recorded")
        return "pending", state or "pending"

    current = body.get("current")
    if not isinstance(current, dict):
        return "unknown", "the release document carries no `current`"
    if sha(current.get("image", "")) != want:
        return "moved", (
            f"the pointer serves {current.get('version') or current.get('image')} instead of {digest}: "
            "the canary vetoed it or another release was promoted"
        )
    if current.get("quarantined"):
        return "quarantined", str(
            current.get("quarantine_reason") or "no reason recorded"
        )
    if current.get("canary_verified"):
        return "verified", str(
            current.get("canary_version_seen") or current.get("version") or ""
        )
    return "pending", "pending"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: fleet-canary-verdict.py <release.json> <digest>", file=sys.stderr)
        return 2
    path, digest = sys.argv[1], sys.argv[2]
    try:
        with open(path, encoding="utf-8") as fh:
            body = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"unknown\tunreadable release document: {exc.__class__.__name__}")
        return 0
    name, detail = verdict(body, digest)
    print(f"{name}\t{detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
