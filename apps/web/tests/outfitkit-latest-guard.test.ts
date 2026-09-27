// Regression test for ERPlora/hub#2259 — the local bench must not test an OutfitKit older than the
// one customers run.
//
// Production (docker/Dockerfile), PRE and CI (test-web.yml, visual-baselines.yml) all install
// `@erplora/outfitkit@latest`, ignoring the pin. The local bench installs whatever
// `pnpm-lock.yaml` pinned, which falls behind with every OutfitKit release: on 2026-09-27 the pin
// was 0.1.84 while `latest` was 0.1.105, and hub#2253 was filed and tested against a bug that was
// already fixed for customers since 0.1.98. The guard below turns that drift into a red bench
// with the command that fixes it, instead of a silent difference.
//
// rv-2265 — and it must not turn red on a RACE: CI and the pre-push gate install `@latest` and then
// spend minutes building before Playwright starts; a release in that gap is not drift. So the
// guard only fails when the install was ALREADY behind when it was made (some newer version had
// been published before node_modules was written); a release that came out after the install is a
// warning (OUTFITKIT_LATEST_NEWER_THAN_INSTALL). Both sides of that boundary are pinned below.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { resolveOutfitkitVersion } from '../outfitkit-version.ts';
import {
  OUTFITKIT_REGISTRY_URL,
  assertOutfitkitIsLatest,
  compareOutfitkitVersions,
  fetchOutfitkitRegistry,
  readInstallTime,
  type OutfitkitRegistry,
} from './outfitkit-latest-guard.ts';

describe('compareOutfitkitVersions (hub#2259)', () => {
  it('REGRESSION: 0.1.84 is BEHIND 0.1.105 (numeric, not lexical, comparison)', () => {
    expect(compareOutfitkitVersions('0.1.84', '0.1.105')).toBe('behind');
  });

  it('the same version is current', () => {
    expect(compareOutfitkitVersions('0.1.105', '0.1.105')).toBe('current');
  });

  it('a local build newer than the published latest is not behind', () => {
    expect(compareOutfitkitVersions('0.1.106', '0.1.105')).toBe('ahead');
  });

  it('a lower minor is behind even with a higher patch', () => {
    expect(compareOutfitkitVersions('0.1.200', '0.2.0')).toBe('behind');
  });

  it('a lower major is behind even with a higher minor', () => {
    expect(compareOutfitkitVersions('0.9.0', '1.0.0')).toBe('behind');
  });

  it('a version it cannot read is unknown, never current', () => {
    expect(compareOutfitkitVersions('0.1.84', 'not-a-version')).toBe('unknown');
    expect(compareOutfitkitVersions('', '0.1.105')).toBe('unknown');
  });
});

// The install was made at INSTALLED_AT; the registry documents below say when each version came out.
const INSTALLED_AT = new Date('2026-09-27T07:48:08.000Z');
const ms = (d: Date, delta: number) => new Date(d.getTime() + delta).toISOString();

function registry(latest: string, published: Record<string, string>): () => Promise<OutfitkitRegistry> {
  return async () => ({ latest, published });
}

describe('assertOutfitkitIsLatest (hub#2259)', () => {
  it('REGRESSION: an install that was already behind when it was made fails with OUTFITKIT_BEHIND_LATEST', async () => {
    const failure = await assertOutfitkitIsLatest({
      readInstalled: () => '0.1.84',
      readInstalledAt: () => INSTALLED_AT,
      fetchRegistry: registry('0.1.105', { '0.1.84': '2026-09-01T00:00:00Z', '0.1.105': ms(INSTALLED_AT, -1) }),
      warn: vi.fn(),
    }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    expect(failure).toMatchObject({
      code: 'OUTFITKIT_BEHIND_LATEST',
      installed: '0.1.84',
      latest: '0.1.105',
    });
  });

  it('rv-2265: latest published one millisecond AFTER the install only warns (release during the run)', async () => {
    const warn = vi.fn();
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.105',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.106', { '0.1.105': '2026-09-26T22:00:00Z', '0.1.106': ms(INSTALLED_AT, 1) }),
        warn,
      }),
    ).resolves.toBe('newer-than-install');
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain('OUTFITKIT_LATEST_NEWER_THAN_INSTALL');
  });

  it('rv-2265: latest published at the very instant of the install is drift, not a race', async () => {
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.105',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.106', { '0.1.106': ms(INSTALLED_AT, 0) }),
        warn: vi.fn(),
      }),
    ).rejects.toMatchObject({ code: 'OUTFITKIT_BEHIND_LATEST' });
  });

  it('a stale pin installed today fails even if the very latest came out after the install', async () => {
    // hub#2253's shape: the lockfile pinned 0.1.84, and 0.1.85 already existed when it was installed.
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.84',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.106', {
          '0.1.84': '2026-09-01T00:00:00Z',
          '0.1.85': '2026-09-02T00:00:00Z',
          '0.1.106': ms(INSTALLED_AT, 60_000),
        }),
        warn: vi.fn(),
      }),
    ).rejects.toMatchObject({ code: 'OUTFITKIT_BEHIND_LATEST', latest: '0.1.106' });
  });

  it('an OLDER version published before the install does not make the install behind', async () => {
    // Only versions NEWER than the installed one count; 0.1.83 existing before the install is irrelevant.
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.84',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.105', {
          '0.1.83': ms(INSTALLED_AT, -5),
          '0.1.105': ms(INSTALLED_AT, 60_000),
        }),
        warn: vi.fn(),
      }),
    ).resolves.toBe('newer-than-install');
  });

  it('without an install time the guard cannot prove a race, so behind fails', async () => {
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.105',
        readInstalledAt: () => null,
        fetchRegistry: registry('0.1.106', { '0.1.106': ms(INSTALLED_AT, 60_000) }),
        warn: vi.fn(),
      }),
    ).rejects.toMatchObject({ code: 'OUTFITKIT_BEHIND_LATEST' });
  });

  it('a newer version with no publish time cannot prove a race either, so behind fails', async () => {
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.105',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.106', {}),
        warn: vi.fn(),
      }),
    ).rejects.toMatchObject({ code: 'OUTFITKIT_BEHIND_LATEST' });
  });

  it('the installed latest passes without a warning', async () => {
    const warn = vi.fn();
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.105',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.105', { '0.1.105': ms(INSTALLED_AT, -1) }),
        warn,
      }),
    ).resolves.toBe('current');
    expect(warn).not.toHaveBeenCalled();
  });

  it('a local build ahead of latest passes (linked OutfitKit under development)', async () => {
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.106',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('0.1.105', {}),
        warn: vi.fn(),
      }),
    ).resolves.toBe('ahead');
  });

  it('an unreachable registry does not block an offline bench, but says so out loud', async () => {
    const warn = vi.fn();
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.84',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: async () => {
          throw new Error('getaddrinfo ENOTFOUND registry.npmjs.org');
        },
        warn,
      }),
    ).resolves.toBe('unknown');
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain('OUTFITKIT_LATEST_UNKNOWN');
  });

  it('an unreadable latest version warns instead of passing silently as current', async () => {
    const warn = vi.fn();
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.84',
        readInstalledAt: () => INSTALLED_AT,
        fetchRegistry: registry('garbage', {}),
        warn,
      }),
    ).resolves.toBe('unknown');
    expect(warn.mock.calls[0][0]).toContain('OUTFITKIT_LATEST_UNKNOWN');
  });
});

describe('fetchOutfitkitRegistry (hub#2259)', () => {
  const doc = { 'dist-tags': { latest: '0.1.106' }, time: { '0.1.105': 'a', '0.1.106': 'b', created: 'c' } };

  it('reads `dist-tags.latest` and every publish time from the full registry document', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(doc)));
    await expect(fetchOutfitkitRegistry(fetchImpl as typeof fetch)).resolves.toEqual({
      latest: '0.1.106',
      published: doc.time,
    });
    expect(fetchImpl).toHaveBeenCalledWith(OUTFITKIT_REGISTRY_URL, expect.anything());
    expect(OUTFITKIT_REGISTRY_URL).toBe('https://registry.npmjs.org/@erplora/outfitkit');
  });

  it('a registry error status is an error, not a version', async () => {
    // The body carries a version on purpose: only the status can reject it.
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(doc), { status: 503 }));
    await expect(fetchOutfitkitRegistry(fetchImpl as typeof fetch)).rejects.toThrow();
  });

  it('a document without a string `dist-tags.latest` is an error', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ time: doc.time })));
    await expect(fetchOutfitkitRegistry(fetchImpl as typeof fetch)).rejects.toThrow();
  });

  it('a document without `time` still yields the latest (no publish times → no race excuse)', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ 'dist-tags': doc['dist-tags'] })));
    await expect(fetchOutfitkitRegistry(fetchImpl as typeof fetch)).resolves.toEqual({
      latest: '0.1.106',
      published: {},
    });
  });

  it('the request is bounded in time (a mute registry must not hang the bench)', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(doc)));
    await fetchOutfitkitRegistry(fetchImpl as typeof fetch);
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});

describe('readInstallTime (hub#2259, rv-2265)', () => {
  it('is the mtime of the workspace node_modules/.modules.yaml that pnpm rewrites on install/add', () => {
    const root = mkdtempSync(join(tmpdir(), 'okguard-'));
    mkdirSync(join(root, 'node_modules'));
    const marker = join(root, 'node_modules', '.modules.yaml');
    writeFileSync(marker, 'layoutVersion: 5\n');
    utimesSync(marker, INSTALLED_AT, INSTALLED_AT);
    expect(readInstallTime(root)?.toISOString()).toBe(INSTALLED_AT.toISOString());
  });

  it('is null when nothing was installed there', () => {
    expect(readInstallTime(mkdtempSync(join(tmpdir(), 'okguard-')))).toBeNull();
  });
});

// The pure pieces above prove the decision; this proves the bench RUNS it. Without the wiring the
// guard is a function nobody calls — the exact gap hub#1250's config test exists for.
describe('playwright.config wires the guard (hub#2259)', () => {
  const saved: Record<string, string | undefined> = {};
  const KEYS = ['HUB_BIND', 'HUB_RUNTIME_URL', 'HUB_WEB_URL', 'HUB_E2E_ASSISTANT_PORT'];
  beforeEach(() => {
    for (const k of KEYS) saved[k] = process.env[k];
  });
  afterEach(() => {
    for (const k of KEYS) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
    vi.unstubAllGlobals();
  });

  it('globalSetup points at the guard file', async () => {
    vi.resetModules();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cfg = (await import('./playwright.config.ts')).default as any;
    expect(cfg.globalSetup).toMatch(/outfitkit-latest-guard\.ts$/);
  });

  it('REGRESSION: the default export fails the bench when a newer one existed before this install', async () => {
    // The real node_modules of this checkout against a version no install can have reached,
    // published long before any install.
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ 'dist-tags': { latest: '999.0.0' }, time: { '999.0.0': '2000-01-01T00:00:00Z' } }),
          ),
      ),
    );
    const guard = await import('./outfitkit-latest-guard.ts');
    await expect(guard.default()).rejects.toMatchObject({ code: 'OUTFITKIT_BEHIND_LATEST' });
  });

  it('the default export lets the bench run when node_modules has the published latest', async () => {
    const guard = await import('./outfitkit-latest-guard.ts');
    const installed = resolveOutfitkitVersion(guard.WEB_DIR);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ 'dist-tags': { latest: installed }, time: {} }))),
    );
    await expect(guard.default()).resolves.toBe('current');
  });
});
