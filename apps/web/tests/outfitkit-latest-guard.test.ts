// Regression test for ERPlora/hub#2259 — the local bench must not test an OutfitKit older than the
// one customers run.
//
// Production (docker/Dockerfile), PRE and CI (test-web.yml, visual-baselines.yml) all install
// `@erplora/outfitkit@latest`, ignoring the pin. The local bench installs whatever
// `pnpm-lock.yaml` pinned, which falls behind with every OutfitKit release: on 2026-09-27 the pin
// was 0.1.84 while `latest` was 0.1.105, and hub#2253 was filed and tested against a bug that was
// already fixed for customers since 0.1.98. The guard below turns that drift into a red bench
// with the command that fixes it, instead of a silent difference.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  OUTFITKIT_LATEST_URL,
  assertOutfitkitIsLatest,
  compareOutfitkitVersions,
  fetchLatestOutfitkitVersion,
  readInstalledOutfitkitVersion,
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

describe('assertOutfitkitIsLatest (hub#2259)', () => {
  it('REGRESSION: an installed OutfitKit behind latest fails with OUTFITKIT_BEHIND_LATEST', async () => {
    const warn = vi.fn();
    const failure = await assertOutfitkitIsLatest({
      readInstalled: () => '0.1.84',
      fetchLatest: async () => '0.1.105',
      warn,
    }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    expect(failure).toMatchObject({
      code: 'OUTFITKIT_BEHIND_LATEST',
      installed: '0.1.84',
      latest: '0.1.105',
    });
  });

  it('the installed latest passes without a warning', async () => {
    const warn = vi.fn();
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.105',
        fetchLatest: async () => '0.1.105',
        warn,
      }),
    ).resolves.toBe('current');
    expect(warn).not.toHaveBeenCalled();
  });

  it('a local build ahead of latest passes (linked OutfitKit under development)', async () => {
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.106',
        fetchLatest: async () => '0.1.105',
        warn: vi.fn(),
      }),
    ).resolves.toBe('ahead');
  });

  it('an unreachable registry does not block an offline bench, but says so out loud', async () => {
    const warn = vi.fn();
    await expect(
      assertOutfitkitIsLatest({
        readInstalled: () => '0.1.84',
        fetchLatest: async () => {
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
        fetchLatest: async () => 'garbage',
        warn,
      }),
    ).resolves.toBe('unknown');
    expect(warn.mock.calls[0][0]).toContain('OUTFITKIT_LATEST_UNKNOWN');
  });
});

describe('fetchLatestOutfitkitVersion (hub#2259)', () => {
  it('reads `version` from the npm registry `latest` document', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ version: '0.1.105' })));
    await expect(fetchLatestOutfitkitVersion(fetchImpl as typeof fetch)).resolves.toBe('0.1.105');
    expect(fetchImpl).toHaveBeenCalledWith(OUTFITKIT_LATEST_URL, expect.anything());
    expect(OUTFITKIT_LATEST_URL).toBe('https://registry.npmjs.org/@erplora/outfitkit/latest');
  });

  it('a registry error status is an error, not a version', async () => {
    // The body carries a version on purpose: only the status can reject it.
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ version: '0.1.105' }), { status: 503 }));
    await expect(fetchLatestOutfitkitVersion(fetchImpl as typeof fetch)).rejects.toThrow();
  });

  it('a document without a string `version` is an error', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}'));
    await expect(fetchLatestOutfitkitVersion(fetchImpl as typeof fetch)).rejects.toThrow();
  });

  it('the request is bounded in time (a mute registry must not hang the bench)', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ version: '0.1.105' })));
    await fetchLatestOutfitkitVersion(fetchImpl as typeof fetch);
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});

describe('readInstalledOutfitkitVersion (hub#2259)', () => {
  it('reads the version the bench actually resolves from node_modules', () => {
    const webDir = mkdtempSync(join(tmpdir(), 'okguard-'));
    const pkgDir = join(webDir, 'node_modules', '@erplora', 'outfitkit');
    mkdirSync(pkgDir, { recursive: true });
    writeFileSync(join(pkgDir, 'package.json'), JSON.stringify({ version: '0.1.84' }));
    expect(readInstalledOutfitkitVersion(webDir)).toBe('0.1.84');
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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('globalSetup points at the guard file', async () => {
    vi.resetModules();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cfg = (await import('./playwright.config.ts')).default as any;
    expect(cfg.globalSetup).toMatch(/outfitkit-latest-guard\.ts$/);
  });

  it('REGRESSION: the default export fails the bench when the registry publishes a newer one', async () => {
    // The real node_modules of this checkout against a `latest` no install can have reached.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ version: '999.0.0' }))),
    );
    const guard = await import('./outfitkit-latest-guard.ts');
    await expect(guard.default()).rejects.toMatchObject({ code: 'OUTFITKIT_BEHIND_LATEST' });
  });

  it('the default export lets the bench run when node_modules has the published latest', async () => {
    const guard = await import('./outfitkit-latest-guard.ts');
    const installed = guard.readInstalledOutfitkitVersion(guard.WEB_DIR);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ version: installed }))),
    );
    await expect(guard.default()).resolves.toBe('current');
  });
});
