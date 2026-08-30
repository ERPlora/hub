// Regression tests for ERPlora/hub#1250.
//
// hub#1240 shipped the first visual baseline (login) with a hand-rolled `test.skip` that fires
// whenever the platform baseline PNG is missing — in ANY environment, CI included. That was the
// right call while no baseline existed (a permanent red for a file nobody had generated yet is
// noise, not a signal). But Ioan flagged the hole it leaves open once the PNGs land
// (https://github.com/ERPlora/hub/issues/1250#issuecomment-5446195002): deleting a baseline in a
// PR makes the case SKIP again instead of failing — a silent green exactly where the contract is
// supposed to catch a regression.
//
// Two independent pieces close that hole, and both are pure decisions worth unit-testing without
// spinning up a browser or the runtime bench:
//   1. `resolveUpdateSnapshotsMode` — Playwright's own `updateSnapshots` default ('missing')
//      CREATES a missing golden and marks the test green, regardless of CI. Only `'none'` makes a
//      missing baseline a hard failure, so CI (outside the dedicated regeneration run) must force it.
//   2. `shouldSkipMissingBaselineLocally` — the custom skip must apply ONLY off CI (a developer's
//      Mac, where the Linux baseline will never match anyway); on CI a missing baseline must fall
//      through to the assertion and fail via (1), never skip.
import { describe, it, expect } from 'vitest';
import { resolveUpdateSnapshotsMode, shouldSkipMissingBaselineLocally } from './visual-baseline-gate';

describe('resolveUpdateSnapshotsMode (hub#1250)', () => {
  it('regenerates every screenshot on the dedicated baseline-update run', () => {
    expect(resolveUpdateSnapshotsMode({ CI: '1', HUB_UPDATE_BASELINES: '1' })).toBe('all');
  });

  it('a normal CI run never recreates a missing baseline — it must fail instead', () => {
    expect(resolveUpdateSnapshotsMode({ CI: '1', HUB_UPDATE_BASELINES: undefined })).toBe('none');
  });

  it('creates missing baselines locally (authoring a brand-new spec on a dev machine)', () => {
    expect(resolveUpdateSnapshotsMode({ CI: undefined, HUB_UPDATE_BASELINES: undefined })).toBe('missing');
  });
});

describe('shouldSkipMissingBaselineLocally (hub#1250)', () => {
  it('never skips on the dedicated baseline-update run, even before the PNG exists', () => {
    expect(shouldSkipMissingBaselineLocally({ CI: '1', HUB_UPDATE_BASELINES: '1' }, false, false)).toBe(false);
  });

  it('REGRESSION: in CI, once this spec already has SOME baseline committed, a missing one must NOT skip (hub#1250)', () => {
    // Before this fix the guard was `!UPDATING_BASELINES && !existsSync(baseline)`, true in every
    // environment — so deleting one PNG out of an already-generated spec flipped the case to a
    // silent, skipped green instead of a red failure naming the missing capture.
    expect(shouldSkipMissingBaselineLocally({ CI: '1', HUB_UPDATE_BASELINES: undefined }, false, true)).toBe(false);
  });

  it('REGRESSION: in CI, a spec whose baseline directory was NEVER generated must still skip loudly (hub#1250 sequencing)', () => {
    // This is what this very PR ships: five brand-new *Visual.spec.ts, zero PNGs committed
    // anywhere in the repo (`visual-baselines.yml` cannot run yet — workflow_dispatch 404s until
    // the file reaches `main`). Without this distinction, flipping the CI skip off unconditionally
    // turns test-web.yml's `e2e` job permanently red for every PR touching apps/web/**, for as
    // long as it takes to land the baselines — a self-inflicted regression, not the one hub#1250
    // set out to close (a baseline DELETED from an already-working contract).
    expect(shouldSkipMissingBaselineLocally({ CI: '1', HUB_UPDATE_BASELINES: undefined }, false, false)).toBe(true);
  });

  it('skips locally when the baseline does not exist yet (a Mac dev machine, hub#1240)', () => {
    expect(shouldSkipMissingBaselineLocally({ CI: undefined, HUB_UPDATE_BASELINES: undefined }, false, false)).toBe(
      true,
    );
    // Outside CI the Linux baseline will never match anyway, so the directory having other
    // viewports already generated changes nothing — always skip on a dev machine.
    expect(shouldSkipMissingBaselineLocally({ CI: undefined, HUB_UPDATE_BASELINES: undefined }, false, true)).toBe(
      true,
    );
  });

  it('never skips once the baseline already exists', () => {
    expect(shouldSkipMissingBaselineLocally({ CI: undefined, HUB_UPDATE_BASELINES: undefined }, true, true)).toBe(
      false,
    );
  });
});
