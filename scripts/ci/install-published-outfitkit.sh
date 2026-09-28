#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Installs into @erplora/web EXACTLY the OutfitKit version that ERPlora/outfitkit
# just announced (`repository_dispatch: outfitkit-published`, hub#2321), so
# `test-web.yml` tests that release the moment it is published.
#
# Why exact and not `@latest`: the notice leaves `publish.yml` seconds after
# `npm publish`, and the registry's metadata is cached for minutes, so `latest`
# can still resolve to the previous release — a green run over the library
# customers already had. Until the registry serves the new version, pnpm answers
# "no matching version": retried, then refused by code.
#
# Input (env):
#   OUTFITKIT_PUBLISHED          the announced version, X.Y.Z (from the payload)
#   OUTFITKIT_PUBLISH_ATTEMPTS   install attempts (default 10)
#   OUTFITKIT_PUBLISH_WAIT       seconds between attempts (default 30)
#   OUTFITKIT_WEB_DIR            the web app (default apps/web; tests override it)
#
# Refusals, by code: outfitkit_published_version_missing,
# outfitkit_published_version_invalid, outfitkit_published_not_installable,
# outfitkit_published_version_mismatch.
#
# Contract: scripts/tests/install-published-outfitkit.test.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
web_dir=${OUTFITKIT_WEB_DIR:-$repo_root/apps/web}
version=${OUTFITKIT_PUBLISHED:-}
attempts=${OUTFITKIT_PUBLISH_ATTEMPTS:-10}
wait_seconds=${OUTFITKIT_PUBLISH_WAIT:-30}

if [ -z "$version" ]; then
    echo "::error::outfitkit_published_version_missing — the outfitkit-published notice carried no client_payload.version"
    exit 1
fi
# The payload comes from another repository: nothing but X.Y.Z reaches a command line.
if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "::error::outfitkit_published_version_invalid — '$version' is not X.Y.Z"
    exit 1
fi

attempt=1
until pnpm --filter @erplora/web add "@erplora/outfitkit@${version}"; do
    if [ "$attempt" -ge "$attempts" ]; then
        echo "::error::outfitkit_published_not_installable — @erplora/outfitkit@${version} could not be installed after ${attempts} attempts"
        exit 1
    fi
    echo "@erplora/outfitkit@${version} not installable yet (attempt ${attempt}/${attempts}); retrying in ${wait_seconds}s"
    attempt=$((attempt + 1))
    sleep "$wait_seconds"
done

installed=$(node -p "require(process.argv[1]).version" "$web_dir/node_modules/@erplora/outfitkit/package.json" 2>/dev/null || true)
if [ "$installed" != "$version" ]; then
    echo "::error::outfitkit_published_version_mismatch — announced ${version}, node_modules holds '${installed}'"
    exit 1
fi

echo "OutfitKit ${version} installed (announced by ERPlora/outfitkit)"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '### OutfitKit %s publicada\n\nEste run prueba `develop` contra `@erplora/outfitkit@%s`, la versión que acaba de anunciar ERPlora/outfitkit (hub#2321).\n' \
        "$version" "$version" >> "$GITHUB_STEP_SUMMARY"
fi
