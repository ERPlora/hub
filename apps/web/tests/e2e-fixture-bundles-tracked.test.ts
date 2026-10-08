// Regression test for ERPlora/hub#2539 — a fixture module whose bundle only exists on one laptop.
//
// The e2e fixtures under `e2e/fixtures/modules/<id>/` are tiny modules the Playwright specs install
// into the real runtime; the spec serves each one's `ui.entry` (`dist/<id>.esm.js`) from disk. The
// repo's `.gitignore` ignores every `dist/`, so a NEW fixture's bundle is silently left out of the
// commit unless it is added with `git add -f` (as `e2e_till`'s was). That is what happened to
// `e2e_report`: green on the machine that wrote it — the file was there — and «Could not load the
// module» in CI, where the checkout has no such file and the spec's asset route answers 404.
//
// The rule is therefore «nothing under the fixtures lives only on this disk»: every file there is
// either tracked or does not exist. It does not demand that each `ui.entry` exists — `e2e_settings`
// names one on purpose and never ships it (its spec only reads the settings tab).
//
// A vitest file and not another Playwright case: it costs milliseconds, needs no browser and no
// database, and fails in `pnpm test` — the local gate that runs BEFORE the push — instead of forty
// minutes into the e2e job. In a CI checkout there is nothing untracked, so it is green there by
// construction; the machine it protects is the one that wrote the fixture.
import { describe, expect, it } from 'vitest';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const FIXTURES = fileURLToPath(new URL('./e2e/fixtures/modules', import.meta.url));

/**
 * Files under the fixtures that are on disk but not in git — ignored ones included.
 *
 * `node_modules/` is left out: it is never part of a fixture, and the fleet's OutfitKit pin drops
 * one into any folder that looks like a module before a test run.
 */
function filesOnlyOnThisDisk(): string[] {
  const out = execFileSync('git', ['ls-files', '-z', '--others', '--ignored', '--exclude-standard', '--', '.'], {
    cwd: FIXTURES,
    encoding: 'utf8',
  });
  return out.split('\0').filter((path) => path && !path.split('/').includes('node_modules'));
}

describe('e2e fixture modules ship everything they have in the repo (hub#2539)', () => {
  it('no fixture file is ignored or untracked (a `dist/` bundle needs `git add -f`)', () => {
    expect(filesOnlyOnThisDisk()).toEqual([]);
  });
});
